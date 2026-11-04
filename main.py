"""Clinic management API (FastAPI + SQLite). Also serves the frontend from ../frontend."""
import os
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db
from security import hash_password, make_token, read_token, verify_password

LOCS = ["Savar clinic", "Enam clinic", "Private chamber"]
CATS = ["Lab report", "Imaging", "Prescription", "Referral letter", "Consent form", "Other"]
STATUSES = ["Pending", "Confirmed", "Completed", "Cancelled"]
METHODS = ["Cash", "Card", "Bank transfer", "Other"]
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".txt", ".docx", ".xlsx", ".csv"}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
MAX_UPLOAD = 10 * 1024 * 1024
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1") == "1"
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def load_secret() -> bytes:
    env = os.getenv("SECRET_KEY")
    if env:
        return env.encode()
    db.DATA_DIR.mkdir(parents=True, exist_ok=True)
    f = db.DATA_DIR / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip().encode()


SECRET = load_secret()
DUMMY_HASH = hash_password("not-a-real-password")
FAILS: dict[str, tuple[int, float]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    c = db.connect()
    db.seed(c, os.getenv("SEED_PASSWORD", "ChangeMe-2026"), demo=os.getenv("SEED_DEMO", "1") == "1")
    c.close()
    yield


app = FastAPI(title="Clinic manager", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- helpers ----------
def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args).fetchall()]


def log(c, user_id, action, detail=""):
    c.execute("INSERT INTO audit(user_id,action,detail) VALUES(?,?,?)", (user_id, action, detail))


def current_user(request: Request, c=Depends(db.get_db)):
    uid = read_token(request.cookies.get("session"), SECRET)
    u = c.execute("SELECT * FROM users WHERE id=? AND active=1", (uid,)).fetchone() if uid else None
    if not u:
        raise HTTPException(401, "Please sign in.")
    return u


def need(*roles):
    def dep(u=Depends(current_user)):
        if u["role"] not in roles:
            raise HTTPException(403, "Your role cannot do this.")
        return u
    return dep


CLINICAL = need("owner", "doctor")
OWNER = need("owner")


def check_doctor(c, doctor_id):
    if not c.execute("SELECT 1 FROM users WHERE id=? AND active=1 AND role IN ('owner','doctor')", (doctor_id,)).fetchone():
        raise HTTPException(400, "Choose an active doctor.")


def check_patient(c, patient_id):
    if not c.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone():
        raise HTTPException(404, "Patient not found.")


DATE = r"^\d{4}-\d{2}-\d{2}$"
TIME = r"^([01]\d|2[0-3]):[0-5]\d$"


# ---------- auth ----------
class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


@app.post("/api/login")
def login(body: LoginIn, response: Response, c=Depends(db.get_db)):
    email = body.email.strip().lower()
    count, until = FAILS.get(email, (0, 0.0))
    if until > time.time():
        raise HTTPException(429, "Too many attempts. Wait a minute and try again.")
    u = c.execute("SELECT * FROM users WHERE email=? AND active=1", (email,)).fetchone()
    ok = verify_password(body.password, u["pw_hash"] if u else DUMMY_HASH)
    if not (u and ok):
        count += 1
        FAILS[email] = (count, time.time() + 60 if count >= 5 else 0.0)
        log(c, None, "login_failed", email)
        c.commit()
        raise HTTPException(401, "Email or password is incorrect.")
    FAILS.pop(email, None)
    response.set_cookie("session", make_token(u["id"], SECRET), httponly=True, samesite="lax",
                        secure=COOKIE_SECURE, max_age=8 * 3600, path="/")
    log(c, u["id"], "login")
    c.commit()
    return {"id": u["id"], "name": u["name"], "role": u["role"]}


@app.post("/api/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie("session", path="/")


@app.get("/api/me")
def me(u=Depends(current_user)):
    return {"id": u["id"], "name": u["name"], "role": u["role"], "email": u["email"]}


class PasswordIn(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(min_length=10, max_length=200)


@app.post("/api/me/password", status_code=204)
def change_password(body: PasswordIn, u=Depends(current_user), c=Depends(db.get_db)):
    if not verify_password(body.current, u["pw_hash"]):
        raise HTTPException(400, "Current password is incorrect.")
    c.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_password(body.new), u["id"]))
    log(c, u["id"], "password_changed")
    c.commit()


# ---------- state ----------
@app.get("/api/state")
def state(u=Depends(current_user), c=Depends(db.get_db)):
    clinical = u["role"] in ("owner", "doctor")
    patients = rows(c, "SELECT id,name,dob,phone,allergies FROM patients ORDER BY id")
    visits: dict[str, list] = {}
    if clinical:
        for v in rows(c, "SELECT patient_id,doctor_id AS did,date,symptoms,diagnosis,rx FROM visits ORDER BY date,id"):
            visits.setdefault(v.pop("patient_id"), []).append(v)
    last = {r[0]: r[1] for r in c.execute("SELECT patient_id, MAX(date) FROM visits GROUP BY patient_id")}
    for p in patients:
        p["visits"] = visits.get(p["id"], [])
        p["last_visit"] = last.get(p["id"])
    out = {
        "doctors": rows(c, "SELECT id,name,spec FROM users WHERE role IN ('owner','doctor') AND active=1 ORDER BY id"),
        "patients": patients,
        "appts": rows(c, "SELECT id,patient_id AS pid,doctor_id AS did,loc,date,time,reason,status FROM appointments"),
        "inv": rows(c, "SELECT no,patient_id AS pid,doctor_id AS did,date,amount,paid,method FROM invoices"),
        "docs": rows(c, "SELECT id,patient_id AS pid,cat,filename AS name,size,date,note FROM documents ORDER BY id DESC") if clinical else [],
        "users": rows(c, "SELECT id,email,name,role,spec,active FROM users ORDER BY id") if u["role"] == "owner" else [],
    }
    return out


# ---------- patients and visits ----------
class PatientIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    dob: str = Field(pattern=DATE)
    phone: str = Field(pattern=r"^[+\d][\d\s]{6,24}$")
    allergies: str = Field("", max_length=300)


@app.post("/api/patients", status_code=201)
def add_patient(body: PatientIn, u=Depends(current_user), c=Depends(db.get_db)):
    if body.dob > date.today().isoformat():
        raise HTTPException(400, "Date of birth cannot be in the future.")
    pid = db.next_patient_id(c)
    c.execute("INSERT INTO patients(id,name,dob,phone,allergies,created_by) VALUES(?,?,?,?,?,?)",
              (pid, body.name.strip(), body.dob, body.phone.strip(), body.allergies.strip() or "None recorded", u["id"]))
    log(c, u["id"], "patient_created", pid)
    c.commit()
    return {"id": pid}


class VisitIn(BaseModel):
    doctor_id: int
    symptoms: str = Field(min_length=1, max_length=2000)
    diagnosis: str = Field(min_length=1, max_length=2000)
    rx: str = Field("", max_length=2000)
    fee: float = Field(0, ge=0, le=100000)


@app.post("/api/patients/{pid}/visits", status_code=201)
def add_visit(pid: str, body: VisitIn, u=Depends(CLINICAL), c=Depends(db.get_db)):
    check_patient(c, pid)
    check_doctor(c, body.doctor_id)
    today = date.today().isoformat()
    c.execute("INSERT INTO visits(patient_id,doctor_id,date,symptoms,diagnosis,rx) VALUES(?,?,?,?,?,?)",
              (pid, body.doctor_id, today, body.symptoms.strip(), body.diagnosis.strip(), body.rx.strip()))
    if body.fee > 0:
        c.execute("INSERT INTO invoices(no,patient_id,doctor_id,date,amount) VALUES(?,?,?,?,?)",
                  (db.next_invoice_no(c), pid, body.doctor_id, today, body.fee))
    log(c, u["id"], "visit_added", pid)
    c.commit()
    return {"ok": True}


# ---------- appointments ----------
class ApptIn(BaseModel):
    patient_id: str
    doctor_id: int
    loc: str
    date: str = Field(pattern=DATE)
    time: str = Field(pattern=TIME)
    reason: str = Field(min_length=1, max_length=200)


@app.post("/api/appointments", status_code=201)
def add_appt(body: ApptIn, u=Depends(current_user), c=Depends(db.get_db)):
    check_patient(c, body.patient_id)
    check_doctor(c, body.doctor_id)
    if body.loc not in LOCS:
        raise HTTPException(400, "Choose one of the clinic places.")
    if not ("08:00" <= body.time <= "17:30"):
        raise HTTPException(400, "Clinic hours are 08:00 to 17:30.")
    if c.execute("SELECT 1 FROM appointments WHERE doctor_id=? AND date=? AND time=? AND status!='Cancelled'",
                 (body.doctor_id, body.date, body.time)).fetchone():
        raise HTTPException(409, "That doctor already has an appointment at this time. Pick another slot.")
    c.execute("INSERT INTO appointments(patient_id,doctor_id,loc,date,time,reason) VALUES(?,?,?,?,?,?)",
              (body.patient_id, body.doctor_id, body.loc, body.date, body.time, body.reason.strip()))
    log(c, u["id"], "appointment_created", f"{body.patient_id} {body.date} {body.time}")
    c.commit()
    return {"ok": True}


class StatusIn(BaseModel):
    status: str


@app.patch("/api/appointments/{aid}")
def set_status(aid: int, body: StatusIn, u=Depends(current_user), c=Depends(db.get_db)):
    if body.status not in STATUSES:
        raise HTTPException(400, "Unknown status.")
    if c.execute("UPDATE appointments SET status=? WHERE id=?", (body.status, aid)).rowcount == 0:
        raise HTTPException(404, "Appointment not found.")
    log(c, u["id"], "appointment_status", f"{aid} {body.status}")
    c.commit()
    return {"ok": True}


# ---------- invoices ----------
class InvoiceIn(BaseModel):
    patient_id: str
    doctor_id: int
    amount: float = Field(gt=0, le=100000)


@app.post("/api/invoices", status_code=201)
def add_invoice(body: InvoiceIn, u=Depends(current_user), c=Depends(db.get_db)):
    check_patient(c, body.patient_id)
    check_doctor(c, body.doctor_id)
    no = db.next_invoice_no(c)
    c.execute("INSERT INTO invoices(no,patient_id,doctor_id,date,amount) VALUES(?,?,?,?,?)",
              (no, body.patient_id, body.doctor_id, date.today().isoformat(), body.amount))
    log(c, u["id"], "invoice_created", no)
    c.commit()
    return {"no": no}


class PayIn(BaseModel):
    amount: float = Field(gt=0)
    method: str


@app.post("/api/invoices/{no}/pay")
def pay(no: str, body: PayIn, u=Depends(current_user), c=Depends(db.get_db)):
    inv = c.execute("SELECT * FROM invoices WHERE no=?", (no,)).fetchone()
    if not inv:
        raise HTTPException(404, "Invoice not found.")
    if body.method not in METHODS:
        raise HTTPException(400, "Choose a payment method.")
    left = round(inv["amount"] - inv["paid"], 2)
    if body.amount > left + 0.001:
        raise HTTPException(400, f"The amount cannot be more than the balance of {left:.2f}.")
    c.execute("UPDATE invoices SET paid=ROUND(paid+?,2), method=? WHERE no=?", (body.amount, body.method, no))
    log(c, u["id"], "payment_recorded", f"{no} {body.amount}")
    c.commit()
    return {"ok": True}


# ---------- documents ----------
@app.post("/api/documents", status_code=201)
async def upload_doc(patient_id: str = Form(...), cat: str = Form(...), note: str = Form("", max_length=300),
                     file: UploadFile = File(...), u=Depends(CLINICAL), c=Depends(db.get_db)):
    check_patient(c, patient_id)
    if cat not in CATS:
        raise HTTPException(400, "Choose a category.")
    name = Path(file.filename or "").name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "This file type is not supported. Use PDF, image, text, Word, Excel or CSV.")
    data = await file.read(MAX_UPLOAD + 1)
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "The file is over 10 MB.")
    stored = f"{uuid.uuid4().hex}{ext}"
    (db.UPLOAD_DIR / stored).write_bytes(data)
    c.execute("INSERT INTO documents(patient_id,cat,filename,stored,size,date,note,uploaded_by) VALUES(?,?,?,?,?,?,?,?)",
              (patient_id, cat, name[:200], stored, len(data), date.today().isoformat(), note.strip(), u["id"]))
    log(c, u["id"], "document_uploaded", f"{patient_id} {name}")
    c.commit()
    return {"ok": True}


@app.get("/api/documents/{doc_id}/file")
def get_doc(doc_id: int, download: int = 0, u=Depends(CLINICAL), c=Depends(db.get_db)):
    d = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    path = db.UPLOAD_DIR / d["stored"] if d else None
    if not d or not path.exists():
        raise HTTPException(404, "Document not found.")
    log(c, u["id"], "document_opened", f"{d['patient_id']} {d['filename']}")
    c.commit()
    inline = d["filename"].lower().endswith(IMAGE_EXT) and not download
    return FileResponse(path, filename=d["filename"],
                        content_disposition_type="inline" if inline else "attachment")


@app.delete("/api/documents/{doc_id}", status_code=204)
def delete_doc(doc_id: int, u=Depends(CLINICAL), c=Depends(db.get_db)):
    d = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not d:
        raise HTTPException(404, "Document not found.")
    if u["role"] != "owner" and d["uploaded_by"] != u["id"]:
        raise HTTPException(403, "Only the owner or the uploader can delete this document.")
    c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    (db.UPLOAD_DIR / d["stored"]).unlink(missing_ok=True)
    log(c, u["id"], "document_deleted", f"{d['patient_id']} {d['filename']}")
    c.commit()


# ---------- team (owner only) ----------
class UserIn(BaseModel):
    email: str = Field(pattern=r"^\S+@\S+\.\S+$", max_length=200)
    name: str = Field(min_length=3, max_length=120)
    role: str = Field(pattern=r"^(owner|doctor|receptionist)$")
    spec: str = Field("", max_length=120)
    password: str = Field(min_length=10, max_length=200)


@app.post("/api/users", status_code=201)
def add_user(body: UserIn, u=Depends(OWNER), c=Depends(db.get_db)):
    try:
        c.execute("INSERT INTO users(email,name,role,spec,pw_hash) VALUES(?,?,?,?,?)",
                  (body.email.strip().lower(), body.name.strip(), body.role, body.spec.strip(), hash_password(body.password)))
    except Exception:
        raise HTTPException(409, "An account with this email already exists.")
    log(c, u["id"], "user_created", body.email)
    c.commit()
    return {"ok": True}


class UserPatch(BaseModel):
    active: bool | None = None
    password: str | None = Field(None, min_length=10, max_length=200)


@app.patch("/api/users/{uid}")
def patch_user(uid: int, body: UserPatch, u=Depends(OWNER), c=Depends(db.get_db)):
    if not c.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
        raise HTTPException(404, "Account not found.")
    if body.active is not None:
        if uid == u["id"]:
            raise HTTPException(400, "You cannot disable your own account.")
        c.execute("UPDATE users SET active=? WHERE id=?", (int(body.active), uid))
        log(c, u["id"], "user_active", f"{uid} {body.active}")
    if body.password:
        c.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_password(body.password), uid))
        log(c, u["id"], "user_password_reset", str(uid))
    c.commit()
    return {"ok": True}


@app.get("/api/audit")
def audit(u=Depends(OWNER), c=Depends(db.get_db)):
    return rows(c, "SELECT a.ts,a.action,a.detail,u.name AS user FROM audit a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200")


@app.get("/healthz")
def healthz():
    return {"ok": True}


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="web")
