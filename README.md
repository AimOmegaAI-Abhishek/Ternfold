# Ternfold — Margin Decision Desk

Persistent, human-reviewed order-margin workspace for the documented India/INR back-to-back MVP. All application records use Supabase PostgreSQL; there is no local database fallback.

## Configure Supabase

Create `%LOCALAPPDATA%\Ternfold\.env` and add the Supabase Session pooler URI:

```text
SUPABASE_DATABASE_URL=postgresql://postgres.PROJECT_REF:DATABASE_PASSWORD@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
```

The configured database password must be URL-encoded when it contains URI-reserved characters.

## Setup and run

```powershell
.\ternfold.ps1 Setup
.\ternfold.ps1 Start
```

Open <http://127.0.0.1:8000/login>. `Setup` applies Alembic migrations to Supabase and creates the labelled synthetic demonstration records. It never creates or starts a local database.

All synthetic accounts use password `TernfoldDemo!`:

| Role | Email |
|---|---|
| Operations | `rohan@example.test` |
| Assigned reviewer | `reviewer@ternfold.test` |
| Decision owner | `meera@example.test` |
| Purchasing | `kavita@example.test` |

Follow [DEMO_GUIDE.md](DEMO_GUIDE.md) for the sales walkthrough.

## Commands

```powershell
.\ternfold.ps1 Setup
.\ternfold.ps1 Start
.\ternfold.ps1 Stop
.\ternfold.ps1 Status
.\ternfold.ps1 Reset-Demo
.\ternfold.ps1 Apply-Retention
```

`Reset-Demo` refuses to run if the selected Supabase database contains a non-synthetic organization. Database changes run through Alembic during `Setup`.

## Optional AI extraction

The same private `.env` can select one provider:

```text
TERNFOLD_AI_PROVIDER=nvidia
NVIDIA_API_KEY=...
NVIDIA_MODEL=deepseek-ai/deepseek-v4-pro-0813
```

OpenRouter and Anthropic adapters are also supported. The core reviewed workflow and deterministic calculations do not require an AI key. Model output is saved only as a draft and never confirms applicability or calculates contribution.

See [OPERATIONS.md](OPERATIONS.md) for retention and pilot boundaries and [REQUIREMENTS_VERIFICATION.md](REQUIREMENTS_VERIFICATION.md) for verification evidence.
