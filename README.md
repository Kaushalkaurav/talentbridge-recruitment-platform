# Talent Bridge V6 — Recruitment Platform (Full source)

Premium responsive recruitment site for India with employer and candidate accounts, hiring enquiries, job applications, candidate profiles, private resume/JD storage and role-restricted admin dashboard. The approved glasses-portrait hero is included locally.

## Local launch

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m app.cli create-admin
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Visit http://127.0.0.1:8000. Admin panel at `/admin`, employer portal at `/hire`, candidate portal at `/candidate/profile`.

The database is created at `data/talentbridge.sqlite3`. Uploads are private in `data/uploads/`. Do not commit either. No real personal data or admin credentials are included.

## V6 improvements

- Admin CSV exports for candidates, hiring enquiries, contacts, applications and jobs. CSV injection mitigation.
- Admin candidate searching by name, skills, role, location, status, and experience.
- Admin job editing as well as creation and publication toggle.
- Basic DOCX zip validation and upload size checks, private document permissions.
- `/healthz` database health check, additional security response headers and Dockerfile.
- Documented deployment requirements and production gaps in `DEPLOYMENT.md`.

## Functional workflows

Employers register -> submit hiring requests (+ optional JD) -> view requests in employer dashboard. Candidates register -> complete their profile, consent and resume -> apply to published jobs -> track applications. Admin users log in -> search candidate database -> download uploaded documents -> update candidate, enquiry, application and contact statuses -> create/edit/publish jobs and export CSV data. Contact form saves requests and SMTP notifications can be sent when configured.

## Tests

```powershell
.venv\Scripts\python.exe -m pip install pytest httpx
.venv\Scripts\python.exe -m pytest -q
```

## Production caveat

This is a complete locally runnable development project, **not a signed-off production launch**. SMTP needs credentials, and deployment requires a persistent data store, stronger identity and file scanning controls, monitored backups, real privacy notices, and additional security testing. See `DEPLOYMENT.md`.

## GitHub and hosting handover

See `GITHUB_AND_DEPLOYMENT.md` for private repository setup and production launch prerequisites. GitHub Actions test workflow is in `.github/workflows/tests.yml`.
