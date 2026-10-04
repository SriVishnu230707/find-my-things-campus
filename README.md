# Campus Lost-and-Found API

Phase 3 stores lost-and-found reports persistently with SQLite, SQLAlchemy, and Alembic.

## Requirements

Python 3.12 or newer. The foundation was verified with Python 3.12.14.

## Setup on Windows (PowerShell)

Run these commands from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .\backend
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
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
    models/          SQLAlchemy report table
    services/        Transactional report operations
  migrations/        Alembic schema revisions
  alembic.ini        Migration configuration
  tests/             HTTP integration tests
  pyproject.toml     Package metadata and pinned direct dependencies
```

Dependencies: FastAPI 0.142.2, Pydantic 2.13.5, Uvicorn 0.53.0, SQLAlchemy 2.1.2, Alembic 1.20.0. Application version: `0.3.0`.

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
$report = @{
    title = 'Laptop Charger'
    description = 'Black Dell 65W charger'
    category = 'electronics'
    location = 'Central Library'
    type = 'lost'
    reported_by = 'Vishnu'
} | ConvertTo-Json
$item = Invoke-RestMethod http://127.0.0.1:8000/items -Method Post -ContentType 'application/json' -Body $report
Invoke-RestMethod "http://127.0.0.1:8000/items/$($item.id)"
Invoke-RestMethod "http://127.0.0.1:8000/items/$($item.id)" -Method Patch -ContentType 'application/json' -Body '{"status":"resolved"}'
Invoke-RestMethod "http://127.0.0.1:8000/items/$($item.id)" -Method Delete
```

The server assigns IDs, UTC timestamps, and initial status `open`. Categories are `electronics`, `clothing`, `documents`, `accessories`, or `other`. Type is `lost` or `found`. Status is `open` or `resolved`; claim statuses arrive with the claims workflow.

Text is trimmed; NUL characters and invalid Unicode surrogates are rejected. Titles require 3–120 characters, descriptions 10–2000, locations 2–150, and reporter names 2–100. Unknown fields are rejected. PATCH accepts only supplied fields, requires at least one change, and rejects explicit null values. IDs and timestamps cannot be edited. Invalid input returns 422; absent reports return 404.

Reports are stored in `backend/data/campus.db` by default, regardless of the directory from which you start the application. Reports survive restarts and code reloads. The database and SQLite sidecar files are excluded from Git. Phase 2 memory reports are not automatically imported.

There is no authentication yet: `reported_by` is an unverified display name, and any client can edit or delete reports. The health endpoint checks API liveness only. Database failures return a generic 503 without SQL or submitted values.

## Database configuration and migrations

To choose a different SQLite file, set an absolute URL before both migration and server commands:

```powershell
$env:DATABASE_URL = 'sqlite:///C:/projects/find my things/backend/data/custom.db'
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

Migrations are explicit: startup refuses an unmigrated database rather than silently creating tables. Re-running `upgrade head` is safe. To add future schema changes, edit the models, generate a revision with `alembic -c backend/alembic.ini revision --autogenerate -m "Describe change"`, inspect the generated migration, then upgrade. Use the virtual environment's Python with `-m alembic` as above.

SQLite serializes writes and waits up to five seconds on a busy database. Partial updates issue a single SQL UPDATE for supplied fields; concurrent edits to the same field still use last-write-wins. Use one worker for local development. PostgreSQL will require its own driver and verification in the deployment phase.

For a simple local backup, stop the server before copying `campus.db` to a safe location. Do not commit reports or database credentials. `downgrade base` drops the reports table and its data; use it only on disposable databases.

## Verification

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

Tests migrate isolated temporary databases and launch their own servers. They cover CRUD, persistence across real process restarts, deletion persistence, rollback, constraints, concurrency, migration roundtrips, metadata consistency, and the existing request protections. They never use your development database.

## Local security limits

Request bodies are limited to 16 KiB, including chunked requests. Lists return up to 100 reports; use `/items?limit=20&offset=20` for subsequent pages. Validation responses omit submitted values. The old 1,000-report memory cap is removed; disk growth and write flooding still require operational limits before deployment.

Hostnames are restricted to `localhost` and `127.0.0.1`. Browser writes accept only origins `http://localhost:8000` and `http://127.0.0.1:8000`; scripts without an Origin header still work. Keep the server on loopback. These protections do not replace authentication or ownership checks.

See [SECURITY.md](SECURITY.md) for fixed findings, remaining threats, and verification evidence.
