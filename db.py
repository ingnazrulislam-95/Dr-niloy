"""SQLite storage: schema, connection helper and first-run seed data."""
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from security import hash_password

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent / "data"))
DB_PATH = DATA_DIR / "clinic.db"
UPLOAD_DIR = DATA_DIR / "uploads"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('owner','doctor','receptionist')),
  spec TEXT NOT NULL DEFAULT '',
  pw_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS patients(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL, dob TEXT NOT NULL, phone TEXT NOT NULL,
  allergies TEXT NOT NULL DEFAULT 'None recorded',
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS visits(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id TEXT NOT NULL REFERENCES patients(id),
  doctor_id INTEGER NOT NULL REFERENCES users(id),
  date TEXT NOT NULL, symptoms TEXT NOT NULL, diagnosis TEXT NOT NULL, rx TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS appointments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id TEXT NOT NULL REFERENCES patients(id),
  doctor_id INTEGER NOT NULL REFERENCES users(id),
  loc TEXT NOT NULL, date TEXT NOT NULL, time TEXT NOT NULL,
  reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending'
);
CREATE TABLE IF NOT EXISTS invoices(
  no TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL REFERENCES patients(id),
  doctor_id INTEGER NOT NULL REFERENCES users(id),
  date TEXT NOT NULL, amount REAL NOT NULL, paid REAL NOT NULL DEFAULT 0, method TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id TEXT NOT NULL REFERENCES patients(id),
  cat TEXT NOT NULL, filename TEXT NOT NULL, stored TEXT NOT NULL,
  size INTEGER NOT NULL, date TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  uploaded_by INTEGER NOT NULL REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  user_id INTEGER, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_appt_doc_time ON appointments(doctor_id, date, time);
"""


def connect() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def get_db():
    c = connect()
    try:
        yield c
    finally:
        c.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    c = connect()
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    c.commit()
    c.close()


def next_patient_id(c) -> str:
    n = c.execute("SELECT MAX(CAST(SUBSTR(id,3) AS INTEGER)) FROM patients").fetchone()[0]
    return f"P-{(n or 1000) + 1}"


def next_invoice_no(c) -> str:
    n = c.execute("SELECT MAX(CAST(SUBSTR(no,5) AS INTEGER)) FROM invoices").fetchone()[0]
    return f"INV-{(n or 0) + 1:04d}"


def seed(c, password: str, demo: bool = True) -> bool:
    """Create the first accounts (and optional demo data) on an empty database."""
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return False
    h = hash_password(password)
    users = [
        ("owner@niloyclinic.demo", "Dr. MH Niloy", "owner", "General practice"),
        ("maria@niloyclinic.demo", "Dr. Maria Tanin", "doctor", "Internal medicine"),
        ("reception@niloyclinic.demo", "Klára Beneš", "receptionist", ""),
    ]
    for email, name, role, spec in users:
        c.execute("INSERT INTO users(email,name,role,spec,pw_hash) VALUES(?,?,?,?,?)", (email, name, role, spec, h))
    if demo:
        d = lambda n: (date.today() + timedelta(days=n)).isoformat()
        pts = [
            ("P-1001", "Jana Procházková", "1984-03-12", "+420 601 112 233", "Penicillin"),
            ("P-1002", "Tomáš Horák", "1971-11-02", "+420 602 445 100", "None recorded"),
            ("P-1003", "Lucie Králová", "2018-06-21", "+420 603 778 910", "Peanuts"),
            ("P-1004", "Petr Veselý", "1959-01-30", "+420 604 300 421", "None recorded"),
            ("P-1005", "Anna Dvořáková", "1992-09-08", "+420 605 884 002", "Latex"),
        ]
        c.executemany("INSERT INTO patients(id,name,dob,phone,allergies,created_by) VALUES(?,?,?,?,?,1)", pts)
        c.executemany(
            "INSERT INTO visits(patient_id,doctor_id,date,symptoms,diagnosis,rx) VALUES(?,?,?,?,?,?)",
            [
                ("P-1001", 1, d(-40), "Persistent cough, mild fever", "Acute bronchitis", "Ambroxol 30 mg, 3x daily for 7 days"),
                ("P-1002", 2, d(-12), "Chest tightness on exertion", "Stable angina, further tests ordered", "Aspirin 100 mg daily"),
                ("P-1004", 1, d(-5), "Elevated blood pressure at home", "Hypertension, grade 1", "Review in 4 weeks, reduce salt"),
            ],
        )
        c.executemany(
            "INSERT INTO appointments(patient_id,doctor_id,loc,date,time,reason,status) VALUES(?,?,?,?,?,?,?)",
            [
                ("P-1001", 1, "Savar clinic", d(0), "09:00", "Follow-up", "Confirmed"),
                ("P-1002", 1, "Enam clinic", d(0), "10:30", "Stress test results", "Pending"),
                ("P-1003", 2, "Private chamber", d(0), "11:15", "Vaccination", "Confirmed"),
                ("P-1005", 2, "Enam clinic", d(0), "12:00", "Follow-up visit", "Pending"),
                ("P-1004", 1, "Savar clinic", d(0), "14:00", "Blood pressure review", "Completed"),
                ("P-1005", 1, "Enam clinic", d(1), "09:30", "General check-up", "Pending"),
            ],
        )
        c.executemany(
            "INSERT INTO invoices(no,patient_id,doctor_id,date,amount,paid,method) VALUES(?,?,?,?,?,?,?)",
            [
                ("INV-0001", "P-1001", 1, d(-40), 45, 45, "Card"),
                ("INV-0002", "P-1002", 2, d(-12), 120, 60, "Bank transfer"),
                ("INV-0003", "P-1004", 1, d(-5), 45, 45, "Cash"),
                ("INV-0004", "P-1004", 1, d(0), 45, 0, ""),
            ],
        )
    c.commit()
    return True
