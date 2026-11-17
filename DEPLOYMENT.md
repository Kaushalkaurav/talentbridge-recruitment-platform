# Talent Bridge deployment readiness

## Local Docker testing

```bash
docker build -t talentbridge .
docker volume create talentbridge-data
docker run --rm -p 8000:8000 -v talentbridge-data:/app/data -e COOKIE_SECURE=0 talentbridge
```

Create an admin with `docker exec -it <container> python -m app.cli create-admin` once the container is running. Use a secure, unique password.

## Important: production state and safety

**Do not deploy this app to ephemeral storage**, including Render's standard ephemeral filesystem, with its current SQLite database and local upload storage: data will be lost on restarts and redeploys. For a pilot use a persistent volume for `/app/data` plus scheduled backups; for public production migrate to managed PostgreSQL, private object storage and a shared rate limiter. This migration is NOT present in this ZIP.

### Configure before a public launch

1. Set `COOKIE_SECURE=1` behind HTTPS; configure trusted reverse proxy and domain.
2. Configure verified SMTP credentials and `ADMIN_NOTIFICATION_EMAIL`.
3. Add verified business email, real contact and legal notices, candidate retention/deletion workflows.
4. Set up user verification, password reset and admin MFA.
5. Add document malware scanning, upload request limits at reverse proxy, and upload observability.
6. Set up monitored, tested backups; error reporting; independent security assessment.
7. Replace in-memory rate limiting with a shared limiter for multiple instances.
8. Enable persistent storage or migrate the data layer before deploying on a managed platform.

A deployment URL is not included and no production service has been deployed.
