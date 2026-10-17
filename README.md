# Campus Lost-and-Found API

Phase 9 adds email verification, password recovery, staff review queues, account controls, and moderation history.

## Verified accounts, recovery, and staff dashboard

Students now verify their email before creating or changing reports/photos, submitting claims, approving claims, or confirming handover. Login, personal reads, notification read controls, and withdrawing an existing claim remain available without verification. Existing accounts are preserved and start unverified; they are not silently declared verified. Staff roles provisioned by the trusted local administrator remain authorized to moderate.

Use **Account → Send verification email**, then open the single-use link or enter the code. Verification links expire after 30 minutes; reset links expire after 15 minutes. **Forgot password?** on the login dialog and **Reset password** in Account start recovery. Password resets preserve password spaces exactly and revoke every previously issued access token for that account. A failed reset rolls back both the password change and link consumption. New requests within one minute are ignored; a later request replaces previous unused links of the same purpose.

| Endpoint | Behavior |
| --- | --- |
| `GET /auth/config` | Public verification/domain/delivery-mode settings; no credentials |
| `POST /auth/verification/request` | JSON email; generic 202 response |
| `POST /auth/verification/confirm` | JSON token; verifies email |
| `POST /auth/password/request` | JSON email; generic 202 response |
| `POST /auth/password/reset` | JSON token and password; consumes link and revokes sessions |
| `GET /staff/summary` | Staff-only overview counts |
| `GET /staff/reports` | Staff-only report filters and pagination |
| `GET /staff/claims` | Staff-only private queue filtered by status |
| `GET /staff/users` | Staff-only profiles and account status; never password hashes |
| `PATCH /staff/users/{user_id}/status` | Staff enables/disables a student account with a moderation reason |
| `GET /staff/audit` | Staff-only paginated moderation history |

Staff see a **Staff dashboard** tab with Overview, Reports, Claim queue, Accounts, and Moderation history. Review a report from the queue to approve/reject or confirm handover. Disabling/reactivating a student revokes old sessions while preserving reports and claims. The web API cannot change roles or disable staff accounts; use the trusted CLI for staff provisioning and role changes. Audit events record account actions, claim decisions, staff report/photo changes, and CLI role/owner changes. They store identifiers/actions rather than passwords, reset links, or private claim evidence, and survive report deletion. They are database history, not a tamper-proof ledger against a database administrator.

### Campus domain configuration

Set `CAMPUS_EMAIL_DOMAINS` to your actual college domains, separated by commas, before starting the server. Matching is exact; list subdomains explicitly. With a configured allowlist, student registration outside those domains is rejected, and verified email must still match the current allowlist for student writes. Restart after changing configuration.

No real college domain has been supplied yet. With an empty allowlist, the app verifies inbox access but sets `campus_verified` to false; it does not claim college membership. `REQUIRE_VERIFIED_EMAIL=true` is the default. Setting it to false is an explicit development compatibility mode; do not use that to bypass verification for a campus pilot. Legacy tests use compatibility mode, while Phase 9 tests exercise mandatory verification and the domain allowlist.

### Local email testing and SMTP

By default, `MAIL_MODE=local` saves private `.eml` messages under ignored `backend/data/mail/`. Messages are not served through the API or website and are not delivered to real inboxes. The local operator can open the recipient's message to follow its link or copy its code. Delete expired development messages when no longer needed, and protect this directory like credentials. `MAIL_DIRECTORY` can point to another private directory. Local delivery is restricted to loopback configuration.

For real delivery, configure `MAIL_MODE=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, and optionally the paired `SMTP_USERNAME`/`SMTP_PASSWORD`. `SMTP_SECURITY` accepts `starttls` (default, normally port 587) or `ssl` (normally port 465); certificate verification is enabled and plaintext delivery is not supported. Supply `PUBLIC_BASE_URL` as the intended origin. Non-loopback origins require HTTPS. Hosting, Host/Origin policy, and public URL changes belong to the deployment phase; setting a public email-link URL alone does not deploy the server.

The code supports SMTP and tests its TLS adapter with a mock server. Actual SMTP delivery still needs provider credentials and an integration check. Email requests return the same message for nonexistent/ineligible accounts and delivery failure; a generic server log identifies failure type without addresses or tokens. Normal responses do not promise constant-time delivery. Single-use token digests are stored in the database; raw tokens appear only in private delivery messages and masked confirmation forms. Links use URL fragments and are removed from the address bar on opening, including same-tab navigation.

Migration 0006 adds verification/activity/session fields, `account_tokens`, and `audit_events` while preserving existing accounts and content. Back up the database and run `alembic upgrade head` before restarting. Existing Phase 8 JWTs remain usable while their account's session version is zero; resets and account status changes invalidate them. Downgrade removes identity flags, recovery tokens, and audit history; use it only on disposable data.

## Photos and notifications

Add an optional photo when posting or editing a report. The website previews the selected image; report cards and details display the uploaded photo. Owners and staff can replace or remove photos on unarchived reports. Reports and their photos are public, so avoid identity documents and private ownership evidence in images.

| Endpoint | Behavior |
| --- | --- |
| `PUT /items/{item_id}/photo` | Owner/staff uploads a multipart file named `photo`; returns updated report |
| `GET /items/{item_id}/photo` | Public normalized JPEG, or 404 if absent |
| `DELETE /items/{item_id}/photo` | Owner/staff removes photo; returns updated report |
| `GET /notifications` | Current user's inbox; `limit` 1–100 (default 20), `offset`, `unread_only` |
| `GET /notifications/unread-count` | Current user's unread count |
| `PATCH /notifications/{notification_id}/read` | Mark an owned notification read; other users' IDs return 404 |
| `POST /notifications/read-all` | Mark only the current user's notifications read |

Each report supports one photo. Inputs must be JPEG or PNG, at most 2 MiB, at most 12 megapixels, and at most 6000 pixels per dimension. Actual image content must match its media type. SVG, GIF, animated PNG, corrupt files, and oversized images are rejected. Files are decoded and re-encoded as a JPEG of at most 1600×1600 pixels (1200×1200 fallback) and 1 MiB. Transparency is flattened on white; EXIF/GPS, other metadata, and original filenames are discarded. Two concurrent decodes are allowed; busy processing returns retryable 503.

Photos are database BLOBs, not files under user-provided paths. Replacement/removal uses the report lock and a transaction; report deletion cascades to its photo. Archival preserves photos and prevents changes. Database backups therefore include photos. `photo_url` is null for reports without a photo; clients cannot submit it or choose storage paths. The existing 16 KiB request cap remains for other endpoints; only the photo PUT endpoint permits 2 MiB plus 16 KiB multipart overhead, while still enforcing the file's own 2 MiB limit.

Report creation and photo upload are separate API operations. If an upload fails after the report is saved, the website identifies the saved report and lets you retry without duplicating it. Notifications are saved in the same transaction as claim changes, so failed claims produce no notifications and notification persistence failure rolls back the claim operation.

The **Notifications** tab shows new submissions to the reporter, decisions/handover to claimants, withdrawals to reviewers, and automatic rejection of other pending claims after handover. For ownerless legacy reports, current staff receive submission/withdrawal updates. Staff decisions also inform the report owner where applicable; the acting account does not receive its own event. Messages contain claim/report IDs and state, never private evidence. Unread counts refresh every 30 seconds while the signed-in page is visible; open the inbox or use **Refresh notifications** to load its latest entries. Individual and bulk read controls persist across restarts. These are in-app notifications, not emails, browser push, or SMS.

Run `alembic upgrade head` after updating. Migration 0005 preserves existing reports/accounts/claims and adds photo versions, `item_photos`, and `notifications`. Existing reports start without photos; historical claims are not backfilled with notifications. Downgrade removes photos and notifications permanently; use it only on disposable data.

## Student website

Open [Find My Things](http://127.0.0.1:8000/campus/) after starting the server. The website is served by FastAPI at the same origin as the API; no separate frontend server, JavaScript build, or CORS changes are needed. Swagger remains at `/docs`, and `/` continues to redirect there for compatibility.

The noticeboard supports keyword/location search, categories, lost/found and status filters, sorting, archival filtering, and pagination. Sign in or create a student account to post/edit reports, access **My reports** and **My claims**, or submit private evidence. Report owners and staff can review claims from report details, approve/reject, confirm physical handover, and archive reports. Destructive actions require a confirmation dialog; workflow conflicts are shown as readable errors.

The frontend uses HTML, CSS, and browser JavaScript in `backend/app/web/`. These assets are included in the Python package. Requests use relative API URLs, and report/evidence text is rendered as text rather than HTML. JWTs stay in memory: refreshing the page signs you out, and signing out or session expiry clears the personal workspace and closes private dialogs. Tokens copied elsewhere remain valid until expiry or account-session revocation.

`GET /items/mine` is authenticated and filters by the current account before applying the same report filters and pagination as `/items`. It never accepts a client-supplied owner ID.

## Requirements

Python 3.12 or newer. The foundation was verified with Python 3.12.14.

## Setup on Windows (PowerShell)

Run these commands from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .\backend
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m app.cli init-secret
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
```

If `python` is unavailable but the Python launcher is installed, use `py -3.12` for the first command. No virtual-environment activation is required.

For the exact dependency versions verified during development, install the lockfile before the editable package:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .\backend
```

## Try the API

- Interactive Swagger UI: http://127.0.0.1:8000/docs
- Alternative documentation: http://127.0.0.1:8000/redoc
- OpenAPI schema: http://127.0.0.1:8000/openapi.json
- Health endpoint: http://127.0.0.1:8000/health
- The root URL redirects to Swagger UI.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected HTTP status: `200`. Expected JSON:

```json
{"status":"ok"}
```

In Swagger UI, expand `GET /health`, select **Try it out**, then **Execute**. Stop the server with `Ctrl+C`. `--reload` is for local development.

## Structure

```text
backend/
  app/
    main.py          Application configuration and router registration
    routers/         HTTP endpoints
    schemas/         Pydantic validation and response contracts
    database.py      Connection configuration and request sessions
    models/          SQLAlchemy report and user tables
    auth.py          Current-user authentication dependency
    security.py      Password hashing and token verification
    cli.py           Local account and ownership administration
    services/        Transactional report operations
  migrations/        Alembic schema revisions
  alembic.ini        Migration configuration
  tests/             HTTP integration tests
  pyproject.toml     Package metadata and pinned direct dependencies
```

Dependencies: FastAPI 0.142.2, Pydantic 2.13.5, Uvicorn 0.53.0, SQLAlchemy 2.1.2, Alembic 1.20.0, argon2-cffi 25.1.0, PyJWT 2.15.1, python-multipart 0.0.32, email-validator 2.3.0, Pillow 12.3.0. Application version: `0.9.0`. The lockfile pins transitive dependencies too.

## Private claims and handover

| Endpoint | Access and behavior |
| --- | --- |
| `POST /items/{item_id}/claims` | Student submits JSON `{"evidence":"Identifying details only the owner knows"}` |
| `GET /claims/me` | Authenticated user reads their own claims |
| `GET /items/{item_id}/claims` | Report owner or staff reads private claims |
| `PATCH /claims/{claim_id}/decision` | Report owner or staff submits `{"decision":"approved"}` or `{"decision":"rejected"}` |
| `POST /claims/{claim_id}/withdraw` | Claimant withdraws a pending or approved claim |
| `POST /claims/{claim_id}/handover` | Report owner or staff confirms return of an approved claim |
| `POST /items/{item_id}/archive` | Report owner or staff archives a report with no active claims |

Claims require an open, unarchived **found** report. Students cannot claim their own reports. Evidence is trimmed, requires 10–2000 characters, and is never included in public report responses. The claim lists support `limit` (1–100, default 100) and `offset`, ordered by newest ID. No other student's claims are exposed through `/claims/me`.

The workflow is `pending → approved → completed`, or `pending → rejected`. Claimants may withdraw pending/approved claims. Repeated or invalid transitions return 409. Approval reserves the item and blocks new submissions, while other pending claims remain available for review. Withdrawal releases the reservation. Handover atomically completes the winning claim, resolves the report, and rejects remaining pending claims. A resolved report cannot be reopened through ordinary PATCH once it has claim history.

Only one active claim per student/report and one approved/completed winner per report are allowed. Database indexes enforce these constraints; report-level write locks serialize claim decisions, submissions, edits, deletion, and archival. Competing approvals return one success and one conflict.

Reports with any claim history cannot be hard-deleted (409). Archive them after active claims are completed, rejected, or withdrawn. Archived reports remain accessible by ID and retain private claim history; public lists exclude them unless `archived=true` is supplied. Archived reports cannot be edited or receive claims. Reports without claims can still be deleted. After any claim has been submitted, report type/status changes must follow the claim workflow; descriptive edits remain possible until archival.

To try this in Swagger: create two student accounts; authorize as the finder and create a found report; log out and authorize as the claimant to submit evidence; authorize as the finder to review, approve, then confirm handover **after returning the item**. The API records the review decision; it cannot independently establish physical ownership. Staff can review legacy reports whose reporter has no account.

Migration 0004 adds archival and claims while preserving existing reports, accounts, ownership, and report IDs. Run `alembic upgrade head` before restarting. Downgrading 0004 permanently removes claim history and archive flags; use downgrade only on disposable databases.

## Accounts and permissions

| Endpoint | Behavior |
| --- | --- |
| `POST /auth/register` | JSON email, display_name, password; creates a student account |
| `POST /auth/login` | Form fields username (email) and password; returns a bearer token valid for 900 seconds |
| `GET /auth/me` | Returns the authenticated user's profile |

In Swagger, first execute `/auth/register`. Click **Authorize**, enter the email as username and the same password, then click **Authorize** and **Close**. Protected requests now send the bearer token. Leave client ID and client secret empty. Reauthorize after the token expires.

Passwords require 12–128 characters and preserve spaces exactly. Display names require 2–100 characters. Emails are normalized to lowercase; duplicate registration returns 409. Registration cannot assign staff privileges. Password hashes are never returned.

Anyone can read reports. Creating a report requires login and eligible verified email for students; editing and deleting also require its owner or a staff account. Missing/invalid credentials return 401; insufficient permissions or required verification return 403. The server assigns `reporter_id` and `reported_by` from the account. These fields cannot be supplied or edited through the report API. Display names are public and do not prove campus identity.

The signing secret is generated once in ignored `backend/data/auth.secret`. Alternatively set a randomly generated `AUTH_SECRET` of at least 32 bytes before starting the server. Keep it private and persistent across restarts. Replacing it invalidates all existing tokens. Swagger logout clears its stored token; it does not revoke a token already copied elsewhere. Roles are checked in the database on every request, so role changes take effect immediately.

Local administration (requires trusted access to the server and database):

```powershell
.\.venv\Scripts\python.exe -m app.cli create-staff --email staff@example.org --name 'Campus Staff'
.\.venv\Scripts\python.exe -m app.cli set-role --email student@example.org --role staff
.\.venv\Scripts\python.exe -m app.cli assign-owner --item-id 1 --email student@example.org
```

Staff creation prompts for a password privately. Accounts created directly by this trusted command have their email flag marked verified by the operator; campus-domain verification is still computed separately. Use `--role student` to demote an account. Assign legacy reports only after verifying their owner; matching display names is insufficient. Ownership reassignment is serialized with the claim workflow and rejects archived reports or a target account with claim history on that report. Refresh tokens and individual-token revocation remain deferred; reset and status changes revoke all account sessions.

## Report API

| Method | Path | Successful response |
| --- | --- | --- |
| POST | `/items` | 201, created report and Location header |
| GET | `/items` | 200, report list (initially empty) |
| GET | `/items/{item_id}` | 200, one report |
| PATCH | `/items/{item_id}` | 200, updated report |
| DELETE | `/items/{item_id}` | 204, no response body |

Example create request (use Swagger UI or PowerShell):

```powershell
$password = Read-Host 'Choose a password (12–128 characters)' -MaskInput # PowerShell 7
$account = @{email='student@example.org'; display_name='Vishnu'; password=$password} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/auth/register -Method Post -ContentType 'application/json' -Body $account
Invoke-RestMethod http://127.0.0.1:8000/auth/verification/request -Method Post -ContentType 'application/json' -Body '{"email":"student@example.org"}'
Read-Host 'Complete email verification through the link/code, then press Enter' | Out-Null
$login = Invoke-RestMethod http://127.0.0.1:8000/auth/login -Method Post -ContentType 'application/x-www-form-urlencoded' -Body @{username='student@example.org'; password=$password}
$headers = @{Authorization="Bearer $($login.access_token)"}
$report = @{
    title = 'Laptop Charger'
    description = 'Black Dell 65W charger'
    category = 'electronics'
    location = 'Central Library'
    type = 'lost'
} | ConvertTo-Json
$item = Invoke-RestMethod http://127.0.0.1:8000/items -Method Post -Headers $headers -ContentType 'application/json' -Body $report
Invoke-RestMethod "http://127.0.0.1:8000/items/$($item.id)"
Invoke-RestMethod "http://127.0.0.1:8000/items/$($item.id)" -Method Patch -Headers $headers -ContentType 'application/json' -Body '{"status":"resolved"}'
Invoke-RestMethod "http://127.0.0.1:8000/items/$($item.id)" -Method Delete -Headers $headers
```

The server assigns IDs, UTC timestamps, and initial status `open`. Categories are `electronics`, `clothing`, `documents`, `accessories`, or `other`. Type is `lost` or `found`. Report status is `open` or `resolved`; claim status is tracked separately.

Text is trimmed; NUL characters and invalid Unicode surrogates are rejected. Titles require 3–120 characters, descriptions 10–2000, locations 2–150, and reporter names 2–100. Unknown fields are rejected. PATCH accepts only supplied fields, requires at least one change, and rejects explicit null values. IDs and timestamps cannot be edited. Invalid input returns 422; absent reports return 404.

Reports are stored in `backend/data/campus.db` by default, regardless of the directory from which you start the application. Reports survive restarts and code reloads. The database and SQLite sidecar files are excluded from Git. Phase 2 memory reports are not automatically imported.

The health endpoint checks API liveness only. Database failures return a generic 503 without SQL or submitted values.

## Database configuration and migrations

After updating, run `.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head` before restarting. Migration 0002 adds listing/filter indexes. Migration 0003 adds accounts and ownership, preserving reports and ID sequences. Existing reports retain their display names and have no owner (`reporter_id: null`); only staff can modify them until a trusted administrator assigns ownership.

To choose a different SQLite file, set an absolute URL before both migration and server commands:

```powershell
$env:DATABASE_URL = 'sqlite:///C:/projects/find my things/backend/data/custom.db'
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

Migrations are explicit: startup refuses an unmigrated database rather than silently creating tables. Re-running `upgrade head` is safe. To add future schema changes, edit the models, generate a revision with `alembic -c backend/alembic.ini revision --autogenerate -m "Describe change"`, inspect the generated migration, then upgrade. Use the virtual environment's Python with `-m alembic` as above.

SQLite serializes writes and waits up to five seconds on a busy database. Partial updates issue a single SQL UPDATE for supplied fields; concurrent edits to the same field still use last-write-wins. Use one worker for local development. PostgreSQL will require its own driver and verification in the deployment phase.

For a simple local backup, stop the server before copying `campus.db` to a safe location. Do not commit reports or database credentials. `downgrade base` drops the reports table and its data; use it only on disposable databases.

## Search and filtering

`GET /items` accepts the following optional query parameters:

| Parameter | Meaning |
| --- | --- |
| `q` | Trimmed substring in title OR description; 1–120 characters |
| `location` | Trimmed location substring; 1–150 characters |
| `category` | electronics, clothing, documents, accessories, other |
| `type` | lost or found |
| `status` | open or resolved |
| `sort` | newest (default) or oldest, based on creation time then ID |
| `limit` | 1–100, default 100 |
| `offset` | Nonnegative signed 64-bit integer, default 0 |

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/items?q=charger&type=found&category=electronics&location=library&status=open&sort=newest&limit=20'
```

Search is case-insensitive for ASCII letters under SQLite's default rules; full Unicode case folding is not provided. It is literal substring matching, not fuzzy search or full-text ranking. `%`, `_`, and `/` are treated literally. All supplied filters are combined with AND around the title/description OR condition. SQLAlchemy binds user values as query parameters.

Filtering and sorting happen in the database before pagination. Results remain a JSON list; no matches returns 200 with `[]`. Invalid or unknown query parameters return 422. Changing the default order from ID ascending to newest first is intentional. Timestamp ties use IDs; editing a report does not change its position. New reports between offset-page requests can shift pages.

Migration 0002 indexes chronological ordering and category/type/status combinations. Substring search still scans text; these indexes do not make arbitrary contains-search fast.

## Run checks

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

Tests migrate isolated temporary databases and launch their own servers. They cover CRUD, persistence, rollback, constraints, concurrency, migration roundtrips, metadata consistency, request protections, account validation, exact password handling, JWT rejection, anonymous/cross-user access, staff moderation, role changes, legacy ownership, and authentication resource limits. They never use your development database.

## Local security limits

Request bodies are limited to 16 KiB, including chunked requests. Lists return up to 100 reports; use `/items?limit=20&offset=20` for subsequent pages. Validation responses omit submitted values. The old 1,000-report memory cap is removed; disk growth and write flooding still require operational limits before deployment.

Hostnames are restricted to `localhost` and `127.0.0.1`. Browser writes accept only origins `http://localhost:8000` and `http://127.0.0.1:8000`; scripts without an Origin header still work. Keep the server on loopback. Authentication endpoints share a process-local limit of 60 requests/minute/client, with bounded limiter memory and at most two concurrent Argon2 operations. Busy hashing returns 503; throttling returns 429. These limits require shared enforcement and trusted proxy configuration before a multi-worker deployment.

See [SECURITY.md](SECURITY.md) for fixed findings, remaining threats, and verification evidence.
