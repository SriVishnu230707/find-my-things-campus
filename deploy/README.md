# Phase 10 deployment and recovery

This is a single-server deployment template, not a running public deployment. It uses Python 3.12, PostgreSQL 17, Redis 7 and Caddy 2. Application dependencies are pinned in `backend/requirements.lock`; container tags track patch releases, so record image digests when releasing. Docker Engine with Linux containers and Compose v2 are required.

## Configure and start

1. Point your actual domain's DNS at the server. Permit inbound TCP 80/443. Keep PostgreSQL and Redis ports private. Install Docker and arrange persistent disks, monitoring and off-host backups.
2. Copy `deploy/production.env.example` to `.env.production` at the repository root. This private file is ignored by Git. Restrict filesystem access to the operator. Compose loads it explicitly; the Python app does not automatically load dotenv files.
3. Set `CAMPUS_DOMAIN` to the hostname, `PUBLIC_BASE_URL` and `TRUSTED_ORIGINS` to its HTTPS origin, and `ALLOWED_HOSTS` to that hostname plus `localhost,127.0.0.1`. Set the actual college email domains and SMTP provider's TLS settings. Configure and verify provider delivery before inviting users.
4. Generate independent random secrets for `AUTH_SECRET`, `METRICS_TOKEN`, `POSTGRES_PASSWORD` and `REDIS_PASSWORD` (at least 32 bytes of randomness). For example, run `python -c "import secrets; print(secrets.token_hex(32))"` separately for each secret. Never paste secrets into Git, issue reports or command history. Preserve the existing signing secret when migrating if existing sessions should remain valid.
5. Set `DATABASE_URL` to `postgresql+psycopg://campus:URL_ENCODED_PASSWORD@db:5432/campus` and `REDIS_URL` to `redis://:URL_ENCODED_PASSWORD@redis:6379/0`. Passwords must match their corresponding environment settings. Set `BACKUP_DIRECTORY` to an existing protected absolute host directory.
6. From the repository root run `docker compose --env-file .env.production -f deploy/compose.production.yml config --quiet`, then `docker compose --env-file .env.production -f deploy/compose.production.yml up --build -d`.
7. Inspect service health and generic startup logs. Check `/health`, `/ready`, `/campus/` and `/docs` over HTTPS. Verify registration, actual email delivery, login, a report/photo, claim approval, handover and notifications using dedicated pilot accounts. Review staff access and allowed origins before opening registration.

Caddy obtains certificates and sets HSTS. Only Caddy publishes ports. Forwarded headers are trusted exclusively from its fixed private address; change that address and the app trust setting together if the subnet conflicts with your network. SMTP has outbound connectivity. The app runs without root privileges with a read-only root filesystem. Database and Caddy state use persistent volumes; never remove those volumes during upgrades.

Compose explicitly disables database/Redis transport TLS only on its isolated Docker bridge. For managed or external services, require PostgreSQL `sslmode=verify-full` with the provider CA and `rediss://` with valid certificates; leave `DB_REQUIRE_TLS` and `REDIS_REQUIRE_TLS` enabled. Redis authentication remains mandatory. This template does not provide host-level high availability.

## Move existing SQLite data

Pause all old-server writes before the final backup and leave them paused until verification completes. Back up the database with the existing application's environment:

```powershell
.\.venv\Scripts\python.exe -m app.ops backup-sqlite --output backups\campus-before-migration.db
```

Protect this backup: it includes users, password hashes, claim evidence, photos and account token digests. The command refuses an existing destination and verifies SQLite integrity. It can take an online snapshot, but pausing writes is required for the final cutover to avoid losing later changes.

Start only PostgreSQL/Redis and run the migration service to create an empty target schema. Both source and target must be at the current Alembic head. Using a trusted local operator environment with access to the target, set `DATABASE_URL` to the new PostgreSQL connection and run:

```powershell
.\.venv\Scripts\python.exe -m app.ops import-sqlite --source backups\campus-before-migration.db --confirm-empty-target
```

For the private Compose database, execute this command in a one-off application container with the backup mounted read-only. Do not expose the database port publicly to perform the import. The importer locks target tables, refuses nonempty targets, copies related rows in one transaction and preserves ID sequence high-water marks. It keeps the SQLite file unchanged. Only run it against a newly provisioned target; PostgreSQL sequences are not transactional, so retrying a failed import may leave harmless ID gaps.

Check counts, representative photos, claims, accounts and migration revision before starting the new app. Preserve the signing secret or deliberately require everyone to log in again. Keep the old server stopped. A rollback after new writes requires a deliberate data reconciliation plan; simply switching back would lose those writes.

## Monitoring and rate limits

`/health` is liveness. `/ready` returns 503 when the database or configured Redis is unavailable; container health checks use readiness. Alert on sustained readiness failure, 5xx responses, disk space, backup age and certificate expiry. Requests receive an `X-Request-ID`; JSON request logs contain route templates, timing and status, not request bodies or raw query strings.

Metrics require `Authorization: Bearer METRICS_TOKEN` and are blocked at Caddy. Scrape through a private operator network. Counters are per process and reset on restart; use a single worker with this template, or configure a monitoring system that aggregates individual process endpoints. Export logs privately and define retention. No external alerting service is provisioned automatically.

Redis enforces shared rolling limits: authentication 60 requests/minute per client IP; authenticated writes 120/minute per user; photo uploads additionally 20/minute per user. Keys use HMAC identifiers. Redis failure returns retryable 503 for guarded operations instead of disabling protection. Development without Redis uses bounded process-local limits. Verify proxy client IP handling if adding another load balancer.

## Backups, restore and releases

Run `docker compose --env-file .env.production -f deploy/compose.production.yml --profile ops run --rm backup` to create a uniquely named PostgreSQL custom dump in `BACKUP_DIRECTORY`. The script checks archive readability. Schedule this command with your host scheduler, encrypt and copy dumps off-host, set a retention policy, and alert on failure. A dump on the same server is insufficient for disaster recovery.

Regularly restore a dump into a **new disposable empty PostgreSQL database**, using `pg_restore --exit-on-error --single-transaction --no-owner --no-privileges`, then verify schema revision, row counts and application flows. An archive listing alone does not prove a successful restore. Choose and measure recovery time/data-loss targets with the campus operator.

Before each upgrade, create and validate a backup, read schema changes and test on a restored copy. The migration service completes before the app starts. Avoid destructive downgrades on live data. Keep the previous application image and recorded image digests; use a compatible previous image or restore into a fresh database when rollback requires schema recovery. Production never runs database downgrade commands automatically.

GitHub Actions runs formatting/lint, SQLite regression tests, dependency consistency, an image build, and disposable PostgreSQL/Redis integration tests. Integration tests require explicitly supplied test URLs and refuse a PostgreSQL database whose name is not `campus_test`. CI does not deploy or receive real production secrets. Real SMTP delivery, public DNS/certificates, off-host backup restore and host operations remain deployment acceptance checks.
