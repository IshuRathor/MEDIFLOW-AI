# Contributing to MEDIFLOW AI

This workflow is for a small team working from Windows desktops. Keep changes focused, preserve patient-data authorization, and coordinate database or API contract changes with the team.

## Set up your workstation

Follow the [Windows setup in README.md](README.md#fresh-windows-setup). Each developer should create their own `backend/.venv`, `backend/.env`, and SQLite database. Do not share or commit local environment files, database files, tokens, API keys, or patient data. Use a shared PostgreSQL database only when the team has explicitly configured and coordinated access to one.

## Branches and commits

1. Start from an up-to-date `main` branch: `git switch main` then `git pull --ff-only`.
2. Create a focused branch, for example `feature/appointment-reminders`, `fix/patient-search-scope`, or `docs/windows-setup`.
3. Commit related changes with a short imperative message, such as `Fix patient search ownership filtering`.
4. Do not commit generated folders (`.venv`, `node_modules`, `dist`), local databases, `.env` files, logs, or secrets.

## Pull requests

- Open a pull request from your branch into `main`; do not push directly to `main` for shared feature work.
- Explain the user-visible change, relevant role/ownership behavior, and any migration or configuration impact.
- Include tests for changed backend behavior, especially authorization and patient/doctor ownership. Never weaken a security assertion to make a change pass.
- If models change, include an Alembic migration. Keep `.env.example` synchronized with configuration changes and use placeholders only.
- Before requesting review, run these commands from the stated directories:

  ```powershell
  Set-Location backend
  .\.venv\Scripts\python.exe -m unittest discover -s tests -t .
  .\.venv\Scripts\python.exe -m compileall -q app tests
  .\.venv\Scripts\python.exe -m alembic upgrade head
  ```

  ```powershell
  Set-Location frontend
  npm ci
  npm run lint
  npm run build
  ```

- Resolve review feedback and confirm CI passes before merging. Use the repository's agreed merge policy; avoid force-pushing shared branches.

## Handling sensitive information

Use synthetic data for development and tests. Do not put real patient data, credentials, tokens, or API keys in source, test fixtures, screenshots, issues, pull requests, or logs. Report suspected exposure to the repository maintainer and do not reproduce the value in a fix or review.
