# GitHub and production deployment handover

## Repository

Intended GitHub owner: `Kaushalkaurav`.
Suggested repository: `talentbridge-recruitment-platform` (**private** initially).

Do not commit `.env`, SQLite databases, candidate documents, employer JDs, backups, or secret tokens. `.gitignore` excludes these local artifacts.

After creating an empty private repository on GitHub, from this extracted project root run:

```bash
git init
git branch -M main
git add .
git commit -m "Initial Talent Bridge V6 application"
git remote add origin https://github.com/Kaushalkaurav/talentbridge-recruitment-platform.git
git push -u origin main
```

GitHub Actions includes a test job on pushes and pull requests.

## Hosting decision and launch blockers

Current app uses **SQLite on local disk and stores private resume/JD files on disk**. Never deploy it on ephemeral app storage: records will disappear after restarts or redeploys. Choose one of:

1. Private/staging pilot: a paid host with a persistent disk mounted at `/app/data`, single app instance, private documents, and tested backups; or
2. Public production: migrate to managed PostgreSQL, private object storage, and shared rate limiting, with migrations and operations testing.

External services and credentials still required:
- Real verified SMTP sender + recipient for alerts.
- HTTPS domain, `COOKIE_SECURE=1`, secure reverse-proxy settings.
- Production access and error monitoring, backups and restore drill.
- Account verification/password reset, admin MFA, secure malware scanner for resumes/JDs.
- Approved privacy notice, retention/deletion workflow and real business contacts.

`DEPLOYMENT.md` contains Docker local testing and more detailed checks.

**Status**: code is locally tested but **not deployed**, and no GitHub repository has been created by this handover.
