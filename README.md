# Campus Lost-and-Found API

Phase 2 adds validated lost-and-found report CRUD to the FastAPI foundation.

## Requirements

Python 3.12 or newer. The foundation was verified with Python 3.12.14.

## Setup on Windows (PowerShell)

Run these commands from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .\backend
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
    models/          Reserved for database models in Phase 3
    services/        Reserved for report business logic
  tests/             HTTP integration tests
  pyproject.toml     Package metadata and pinned direct dependencies
```

Dependencies: FastAPI 0.142.2, Pydantic 2.13.5, Uvicorn 0.53.0. The application version, `0.2.0`, is separate from dependency versions. FastAPI installs a compatible Starlette dependency automatically.

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

Text is trimmed. Titles require 3–120 characters, descriptions 10–2000, locations 2–150, and reporter names 2–100. Unknown fields are rejected. PATCH accepts only supplied fields, requires at least one change, and rejects explicit null values. IDs and timestamps cannot be edited. Invalid input returns 422; absent reports return 404.

Storage is process-local and resets on restart or code reload. Use one server worker. There is no authentication yet: `reported_by` is an unverified display name, and any client can edit or delete reports. Persistence and permissions arrive in later phases. The health endpoint checks API liveness only.

## Verification

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

Tests launch and stop their own server on a temporary local port. They cover CRUD, partial updates, validation, missing IDs, generated metadata, and OpenAPI registration.
