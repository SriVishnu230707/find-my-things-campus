# Campus Lost-and-Found API

Phase 1 provides a runnable FastAPI backend, a typed health endpoint, and automatic API documentation.

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
  tests/             Reserved for future behavioral tests
  pyproject.toml     Package metadata and pinned direct dependencies
```

Dependencies: FastAPI 0.142.2, Pydantic 2.13.5, Uvicorn 0.53.0. The application version, `0.1.0`, is separate from dependency versions. FastAPI installs a compatible Starlette dependency automatically.

The health endpoint checks API liveness only. Report CRUD, persistence, authentication, and the student frontend belong to later phases.
