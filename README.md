# Dr. MH Niloy’s Clinic – practice manager

A small clinic system with a real backend: sign-in, roles, patients, visit notes, appointments across three places
(Savar clinic, Enam clinic, Private chamber), billing, and a document archive. Works on desktop and phones.

- **Backend:** FastAPI + SQLite (`backend/`). Passwords are hashed (scrypt), sessions are signed HttpOnly cookies,
  every important action is written to an audit table, uploads are stored on disk outside the web root.
- **Frontend:** plain HTML, CSS and JavaScript (`frontend/`), served by the same FastAPI app.

## Run it on your computer

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
COOKIE_SECURE=0 uvicorn main:app --reload               # Windows PowerShell: $env:COOKIE_SECURE="0"; uvicorn main:app --reload
```

Open http://localhost:8000. On the first start the database is created and seeded:

| Account | Email | Role |
|---|---|---|
| Dr. MH Niloy | owner@niloyclinic.demo | Clinic owner |
| Dr. Maria Tanin | maria@niloyclinic.demo | Doctor |
| Klára Beneš | reception@niloyclinic.demo | Receptionist |

The password for all three is `ChangeMe-2026`, or whatever you set in `SEED_PASSWORD`.
**Change every password after the first sign-in** (Change password button, or Team > Reset password as owner),
and replace the demo emails by adding real accounts in the Team page.

## Put it on GitHub and deploy

GitHub stores the code. GitHub Pages cannot run a Python backend, so deploy the repo to a host that runs Docker.

```bash
git init && git add . && git commit -m "Clinic manager"
git branch -M main
git remote add origin https://github.com/YOUR-NAME/clinic-manager.git
git push -u origin main
```

Then, for example on **Render**: New > Blueprint > pick the repo (it reads `render.yaml`), enter `SEED_PASSWORD`
when asked, deploy. Railway and Fly.io work the same way with the `Dockerfile`.
Whatever host you use, it **must** keep the `/data` folder on a persistent disk or volume, because the database
and uploaded files live there. Without it, everything is lost on each redeploy.

## Settings (environment variables)

| Name | Meaning | Default |
|---|---|---|
| `SECRET_KEY` | Signs session cookies. Set a long random value in production. | generated into `data/secret.key` |
| `SEED_PASSWORD` | Password for the three first accounts | `ChangeMe-2026` |
| `SEED_DEMO` | `1` adds demo patients and appointments on first start, `0` starts empty | `1` |
| `COOKIE_SECURE` | `1` sends the session cookie over HTTPS only. Use `0` only for local http. | `1` |
| `DATA_DIR` | Where the database and uploads are stored | `backend/data` |

## Who can do what

| | Owner | Doctor | Receptionist |
|---|---|---|---|
| Patients, appointments, invoices, payments | yes | yes | yes |
| Visit notes and diagnoses | yes | yes | no |
| Archive (documents) | yes | yes | no |
| Team accounts, password resets, audit log | yes | no | no |

The audit log is available to the owner at `/api/audit` (a screen for it is not built yet).

## Before real patient data

This is a solid starting point, not a certified medical product. Before storing real patient information:
use HTTPS only, set `SECRET_KEY`, back up `/data` regularly (database and uploads together), add the
privacy notices and data-processing agreements your country requires (GDPR if you serve EU patients),
and consider two-factor sign-in and per-doctor patient privacy.

## Not built yet

Per-doctor private patient lists, an audit-log screen, printable prescriptions and certificates,
reports and CSV export, appointment reminders, and place-specific opening hours.
