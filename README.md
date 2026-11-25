# MEDIFLOW AI

MEDIFLOW AI is a role-based hospital operations platform built with FastAPI, PostgreSQL/SQLite, React, Vite, and Gemini-assisted multi-agent workflows.

## Features

- Administrator, Doctor, Finance Staff, and Patient dashboards
- JWT authentication and role-based authorization
- Patient and doctor ownership restrictions
- Slot-based patient booking and cancellation requests with doctor review
- Doctor briefings, weekly workload and assigned-patient appointment timelines
- Billing, payments, INR finance reports and interactive charts
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

One authenticated orchestrator and ToolRegistry serve all four workspaces. The backend resolves account roles, validates tool inputs and checks ownership. Support and triage are shared capabilities.

| AI experience | Account role | Implemented capabilities |
|---|---|---|
| Patient AI | `patient` | Doctor and slot selection, booking and cancellation requests, own appointment and billing history |
| Doctor AI | `clinician` | Daily briefing, pending queues, calendar-week workload and appointments for assigned patients |
| Finance AI | `staff` | Collections, expenses, balances, month and quarter comparisons, interactive INR charts, unusual expense candidates and a conditional baseline forecast |
| Admin AI | `admin` | Existing administrative workspace with account approval, operational dashboard and authorized shared AI tools, including Finance reports |

Finance reports use recorded data in IST. Forecasts require six completed months with positive recorded collections. Expense categories are available from the database. Department expense attribution and a dedicated Admin analytics agent are future work.

## Project layout

```text
backend/app/ai/        Active orchestrator, tool registry and Gemini client
backend/app/api/       Authentication, dashboards, scheduling, billing and chat
backend/app/services/  Appointment, doctor, finance and triage logic
backend/app/models/    SQLAlchemy models
backend/migrations/    Alembic migrations
backend/tests/         Backend tests
frontend/src/          React workspaces, chat and report rendering
frontend/tests/        Frontend tests
```

## Required software

- Windows 10/11
- Python 3.12.x (required for the pinned Windows database driver)
- Node.js 20.19 or newer in the 20.x line, or 22.12 or newer
- npm 10 or newer
- PostgreSQL only when using shared/hosted database mode
- Git

Check versions:

```powershell
python --version
node --version
npm --version
git --version
```

## Fresh Windows setup

Clone the repository and enter the project:

```powershell
git clone https://github.com/IshuRathor/MEDIFLOW-AI.git
Set-Location MEDIFLOW-AI
```

Create a per-developer Python environment and install the backend dependencies:

```powershell
Set-Location backend
py -3.12 -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` for this computer. Generate a private development JWT secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and replace the placeholder. Keep `.env` private; it is ignored by Git. Leave `DATABASE_URL=sqlite:///./hospital.db` for an isolated local database. The database file is created under `backend/` when migrations run.

Initialize the database and start the API (from `backend/`):

```powershell
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second PowerShell terminal, install the exact frontend dependencies from the lockfile and start Vite:

```powershell
Set-Location MEDIFLOW-AI\frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173/`. The API is at `http://127.0.0.1:8000`; interactive documentation is at `http://127.0.0.1:8000/docs`. The frontend defaults to `http://localhost:8000/api`. If needed, set `VITE_API_URL=http://127.0.0.1:8000/api` in `frontend/.env.local` and restart Vite. Add the frontend origin to `CORS_ORIGINS` in `backend/.env` if using a different frontend URL.

Use SQLite for each developer's local work. For a shared PostgreSQL environment, install/run PostgreSQL separately and configure each authorized developer's `DATABASE_URL` privately in their own `backend/.env` (for example, `postgresql+psycopg2://user:password@localhost:5432/hospital_management`). Do not share a local SQLite file or commit database files. Shared databases contain shared data, so coordinate before using one.

`GEMINI_API_KEY` is optional; core CRUD and deterministic triage work without it. Without a key, AI chat uses deterministic fallback behavior. `REDIS_URL` is also optional; without Redis, rate limits are process-local.

## Authentication

Use **Create an account** on the sign-in page. On a fresh database, select **Administrator** for the first account and then sign in as Administrator. The first registration through `POST /api/auth/register` automatically becomes an approved administrator. A fresh install contains no seeded accounts or patients. After the first registration, patients can register and sign in immediately. Doctor, Finance staff, and administrator registrations require review in **Accounts** by an existing administrator.

To try the booking workflow, register and approve a doctor, sign in as that doctor to configure availability, then register a patient and request a slot. Use synthetic records in local development. For direct API calls, use `POST /api/auth/login` and send the returned token as `Authorization: Bearer <token>`.

Set a strong `JWT_SECRET_KEY` before sharing the environment or deploying it.

## Delivery phases

The repository includes local setup, role-based workflows, relational constraints and migrations, an operational dashboard, deterministic triage, optional Gemini orchestration, and automated tests. Production deployment, observability, and clinical validation require separate planning and are not implied by the local development setup.

## Controlled AI workflow

The AI chat endpoint now returns structured responses and maintains conversation
history separately for each authenticated user and conversation ID:

- `POST /api/ai/chat`
- `GET /api/ai/conversations/latest`
- `POST /api/ai/conversations/{conversation_id}/cancellation-selection`
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
- Request cancellation, then approve or reject it from the doctor's request queue
- Reschedule appointment
- Generate a bill or record a payment through AI

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
npm ci
npm run dev -- --host 127.0.0.1
```

The frontend runs at `http://127.0.0.1:5173/` by default.

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
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
```

```powershell
Set-Location frontend
npm test
npm run lint
npm run build
```

The lint script uses Oxlint. If an API feature works in tests but the browser
finds an older route or tool, restart Uvicorn from the current checkout. For
database errors, check the working directory and `DATABASE_URL`, then run
`python -m alembic current` and `python -m alembic heads`. If Vite cannot
reach the API, verify the URL includes `/api` and the frontend origin is allowed.
For Windows activation errors, use the process-scoped execution policy above,
or invoke `backend\.venv\Scripts\python.exe` directly.

`HOSPITAL_TIMEZONE` controls relative booking dates where named timezone data
is available. Without it, the backend falls back to the machine's local
calendar when the configured zone cannot be loaded.

## Security

- Never commit `.env`, API keys, passwords, JWT secrets or database credentials.
- Never commit local databases or private patient, bill or payment data.
- Keep `GEMINI_API_KEY` in environment variables.
- Use HTTPS and strong secrets in production.
- Repository hosting does not remove secrets already exposed in Git history.
