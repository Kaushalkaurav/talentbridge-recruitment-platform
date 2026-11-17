# Talent Bridge — Recruitment Platform

Talent Bridge is a recruitment and placement platform for employers and job seekers in India.

## Project package

The full-stack source package is **TalentBridge_V6_GitHub_Ready.zip**, prepared separately. The project uses Python, FastAPI, Jinja2, SQLite for local development, private resume/JD uploads, employer and candidate accounts, job applications, and an admin dashboard.

**Important:** A README-only repository is not a deployed or functional application. Upload the extracted **contents** of the ZIP (not the ZIP itself) to the repository root before deploying.

## Local setup after source upload

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m app.cli create-admin
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Production blockers

- Use durable database and private document storage; do not use temporary disks for candidate records.
- Set secure session configuration and HTTPS, admin access controls, and backup policies.
- Supply SMTP settings for notifications, and approved company contact / privacy details.
- Add malware scanning, privacy and retention controls, and complete external security testing.
- Never commit .env secrets, `data/*.sqlite3`, or `data/uploads/`.

The current repository is not evidence of a live deployment.
