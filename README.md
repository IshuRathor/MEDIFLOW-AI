# MEDIFLOW AI

MEDIFLOW AI is a role-based hospital operations platform built with FastAPI, PostgreSQL/SQLite, React, Vite, and Gemini-assisted multi-agent workflows.

## Features

- Administrator, Doctor, Finance Staff, and Patient dashboards
- JWT authentication and role-based authorization
- Patient and doctor ownership restrictions
- Appointment scheduling and doctor availability management
- Billing, payments, financial summaries and transaction history
- AI-assisted triage, hospital operations and support
- Database-backed conversation history and expiring approval records
- Deterministic fallback routing when Gemini is unavailable

## Technology stack

- Frontend: React 19, TypeScript, Vite
- Backend: FastAPI, SQLAlchemy, Alembic
- Database: PostgreSQL for shared environments, SQLite for local development
- AI: Google Gemini with registered function tools
- Authentication: JWT with PBKDF2 password hashing

## Architecture

The frontend communicates with FastAPI REST endpoints. The backend separates authentication, operational models, role-specific dashboards, appointment scheduling, billing, and AI orchestration.

The AI system uses one main orchestrator and specialized Hospital, Finance, Support and Triage behaviors backed by a validated tool registry. Sensitive operations require explicit user approval, and tools enforce server-side authorization and ownership.

## Phase 1: Run the backend

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. Interactive API documentation is available at `http://localhost:8000/docs`.

SQLite is used by default for local development. Set `DATABASE_URL` in `backend/.env` to use PostgreSQL.

`GEMINI_API_KEY` is required only for the AI chat and AI routing features. Core CRUD and triage endpoints do not require it.

## Authentication

The first account is created through `POST /api/auth/register` and receives the `admin` role. Once that account exists, public registration is closed. Use `POST /api/auth/login` to obtain a bearer token, then send it as `Authorization: Bearer <token>` when calling operational, triage, or AI endpoints.

Set a strong `JWT_SECRET_KEY` before sharing the environment or deploying it.

## Delivery phases

1. Backend foundation and reproducible local setup
2. Secure identity, roles, API contracts, and database integrity (constraints complete; migrations next)
3. Professional operations dashboard and patient workflows
4. Production-grade AI orchestration and clinical safety controls
5. Tests, migrations, observability, deployment, and hardening

## Controlled AI workflow

The AI chat endpoint now returns structured responses and maintains conversation
history separately for each authenticated user and conversation ID:

- `POST /api/ai/chat`
- `POST /api/ai/approvals/{approval_id}/approve`
- `POST /api/ai/approvals/{approval_id}/reject`
- `DELETE /api/ai/conversations/{conversation_id}`

AI chat requests use deterministic triage before model routing, a tool registry
for database-backed reads, database-backed conversation history, execution
traces, and expiring approval records for booking and cancellation operations.
The existing REST endpoints remain the authoritative implementation of patient,
doctor, appointment, billing and payment operations.

The orchestrator now sends registered tool schemas to Gemini 2.5 Flash. Gemini
may request read tools or sensitive-write proposals, but it cannot execute
arbitrary code or SQL. Arguments are validated, tool execution is bounded,
read tools can retry once, and write operations return an approval record for
explicit user confirmation.

Implemented approval actions:

- Create appointment
- Cancel appointment
- Reschedule appointment

Conversation messages and approvals are stored per authenticated user.
The API isolates arbitrary conversation IDs, rejects cross-user approval
ownership, expires approvals after ten minutes, and applies a per-user AI
chat rate limit.

## Production configuration

Set these environment variables outside development:

```text
ENVIRONMENT=production
JWT_SECRET_KEY=<random-secret-at-least-32-characters>
DATABASE_URL=postgresql://...
CORS_ORIGINS=https://hospital.example.com
GEMINI_API_KEY=<optional-but-required-for-Gemini-routing>
REDIS_URL=redis://redis.example:6379/0
```

The application refuses to start in production without a strong JWT secret and
explicit CORS origins. An omitted `REDIS_URL` uses process-local fallback
rate limiting; Redis is required for horizontally scaled deployments.

## Health checks

- `/health/live` verifies process liveness.
- `/health/ready` verifies database readiness and Gemini configuration state.
- `/health` remains the basic application health endpoint.

## Database backup and restore

PostgreSQL:

```powershell
pg_dump --format=custom --dbname="$env:DATABASE_URL" --file=mediflow.backup
pg_restore --clean --if-exists --dbname="$env:DATABASE_URL" mediflow.backup
```

Before restore, stop application workers, verify the target environment,
restore during a maintenance window, run `alembic upgrade head`, and run the
integration suite against a restored staging copy.

## Frontend setup

```powershell
Set-Location frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173/` by default.

## Environment variables

Copy `backend/.env.example` to `backend/.env` and replace placeholders outside development. Never commit `.env`.

Required for production:

- `ENVIRONMENT=production`
- `JWT_SECRET_KEY` of at least 32 characters
- `DATABASE_URL`
- Explicit `CORS_ORIGINS`

`GEMINI_API_KEY` is optional for core CRUD and is required for Gemini orchestration. Redis is recommended for shared or horizontally scaled deployments.

## Tests and validation

```powershell
Set-Location backend
.\venv\Scripts\python.exe -m unittest discover -s tests -t .
.\venv\Scripts\python.exe -m alembic current
.\venv\Scripts\python.exe -m alembic heads
```

```powershell
Set-Location frontend
npm run lint
npm run build
```

## Security

- Never commit `.env`, API keys, passwords, JWT secrets or database credentials.
- Never commit local databases or private patient, bill or payment data.
- Keep `GEMINI_API_KEY` in environment variables.
- Use HTTPS and strong secrets in production.
- Repository hosting does not remove secrets already exposed in Git history.