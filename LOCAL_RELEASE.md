# Phase 11: final localhost release

Release 0.11.0 completes the local implementation and handover. It includes reports/search, accounts, ownership controls, claims/approval/handover, photos, notifications, campus email verification, recovery, staff moderation and operational tooling. Public deployment is optional and separate; see `deploy/README.md` if that goal changes.

## First-time setup on Windows

Install Python 3.12 or newer. In PowerShell at the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e backend
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\scripts\Start-Campus.ps1
```

The launcher initializes a private signing secret if needed and starts Uvicorn on `127.0.0.1:8000`. It leaves an existing secret intact, refuses to replace a running service, and does not install packages or migrate databases automatically. Existing databases must be backed up before applying upgrades. The application's startup refuses stale schema revisions.

Process environment variables override defaults; `.env.example` documents them but is not automatically loaded. Local defaults use SQLite at `backend/data/campus.db`, local `.eml` delivery, required email verification, and an empty campus domain allowlist. If a prior session configured production services, start a clean PowerShell session and deliberately choose the desired local settings. The localhost launcher refuses `APP_ENV=production`.

## Daily operation and final acceptance

Start with `./scripts/Start-Campus.ps1`. Keep its terminal open. Open `http://127.0.0.1:8000/campus/` for the website and `/docs` for Swagger. Stop with Ctrl+C in that terminal; do not kill unrelated processes listening on port 8000.

In a second PowerShell terminal, run:

```powershell
.\scripts\Start-Campus.ps1 -CheckOnly
# Equivalent portable Python command:
.\.venv\Scripts\python.exe -m app.acceptance --base-url http://127.0.0.1:8000
```

The command returns JSON with 15 named checks and exits 0 only when all pass. It reads health/readiness, release version, site assets, documentation, required verification, security headers/request IDs, anonymous account/notification/staff protections, protected metrics, and inaccessible private database/mail paths. It sends no authenticated requests, creates no accounts/reports/claims and does not expose response bodies or exception details in its report. Connections time out; redirects are refused and responses are bounded. `-CheckOnly` does not start a server. A failure means inspect the named check, start/configure the app if necessary, and rerun. This is a smoke check, not a substitute for the workflow tests below.

Run the complete regression suite before release or after code changes:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

Tests use isolated databases and exercise report/account/privacy/photo/claim/notification/recovery/staff flows and concurrency. Four PostgreSQL/Redis tests skip unless explicit disposable infrastructure URLs are supplied; GitHub Actions supplies those services and also builds and starts the Linux container. CI is a test pipeline, not public deployment.

With Node.js 22 or newer available, run `node --test backend/tests/browser_logic.cjs` for browser-function regressions. These tests use Node's built-in runner and the real frontend functions, with mocked browser surfaces; they require no npm packages. They cover blocked theme storage, malformed API responses, expired/stale sessions and delayed dialog errors. GitHub Actions runs them alongside the backend suite. Actual Edge checks separately verify rendering and browser integration.

## Local email and staff handover

Create a student account in the UI, request verification and open its private message in `backend/data/mail/` to follow the verification link or copy the code. Local mode does not send real email. Avoid sharing these messages or placing them under a public directory; they contain live tokens. Recovery uses the same private delivery directory. An empty campus allowlist proves inbox access only; it does not establish membership of a real college.

Provision a staff account from the trusted operator terminal:

```powershell
.\.venv\Scripts\python.exe -m app.cli create-staff --email staff@example.org --name "Campus Staff"
```

Use your own intended address; the shown address is only an example. The CLI prompts privately for the password. For an existing account use `set-role --email ADDRESS --role staff`. Never let students run operator commands or read the database/signing secret. Staff creation is explicit; the release does not ship a default administrator password.

Final operator walkthrough with dedicated test accounts: verify two students, post a found report with a photo, submit private ownership evidence as the other student, approve and complete handover as the reporter, check both notification inboxes, and inspect the staff dashboard/audit history. Exercise password reset and verify the old session stops working. Archive the test report when finished. Recheck after restarting to confirm persistence. Automated regression tests cover these behaviors without adding demo records to the normal database.

## Preserve and recover local data

```powershell
.\.venv\Scripts\python.exe -m app.ops backup-sqlite --output backups\campus-release-backup.db
```

Choose a new filename each time; existing backups are never overwritten. The backup is integrity-checked and contains sensitive campus data. Keep an additional private copy on another device. Keep `backend/data/auth.secret` separately with restricted access if sessions should survive a restore. Losing it requires intentionally issuing a new secret and signing in again.

To restore, stop the app, preserve the current database, and copy the selected backup to a **new** database path. Point `DATABASE_URL` to that absolute SQLite URL, check migrations, start and run acceptance plus representative workflow checks. Do not overwrite an open database or delete its journal/WAL files. Never run `alembic downgrade base` on data you want to preserve.

Localhost access is limited to this computer. A second computer's `localhost` refers to that computer, not this server. Real SMTP, public HTTPS, campus-domain verification, off-host restore drills, shared infrastructure capacity and external availability monitoring are outside this local release's verified scope.
