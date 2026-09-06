# Ternfold — Margin Decision Desk

Persistent, human-reviewed order-margin workspace for the documented India/INR back-to-back MVP.

## Open the synthetic demo

Open PowerShell in this folder and run:

```powershell
.\ternfold.ps1 Setup
.\ternfold.ps1 Start
```

Open <http://127.0.0.1:8000/login>. Setup creates a separate PostgreSQL 18 cluster under `%LOCALAPPDATA%\Ternfold` on port `55432`; it does not touch a server on port 5432.

All synthetic accounts use password `TernfoldDemo!`:

| Role | Email |
|---|---|
| Operations | `rohan@example.test` |
| Assigned reviewer | `reviewer@ternfold.test` |
| Decision owner | `meera@example.test` |
| Purchasing | `kavita@example.test` |

Follow [DEMO_GUIDE.md](DEMO_GUIDE.md) for the repeatable sales walkthrough.

## Everyday commands

```powershell
.\ternfold.ps1 Start
.\ternfold.ps1 Stop
.\ternfold.ps1 Status
.\ternfold.ps1 Test
.\ternfold.ps1 Reset-Demo
.\ternfold.ps1 Apply-Retention
```

`Test` uses the separate `ternfold_test` database and `tmp\test-storage`. It cannot alter the live demo case. `Reset-Demo` refuses to run if the selected database contains any non-synthetic organization. It deletes and recreates synthetic records only.

Database changes run through Alembic during `Setup` (`alembic upgrade head`). Evidence and reports are private application files under `%LOCALAPPDATA%\Ternfold\storage` in the local profile.

## Supabase and optional AI

Run local `Setup` once to create `%LOCALAPPDATA%\Ternfold\.env` from `.env.example`. Real credentials go in that local file, outside OneDrive. Put the Supabase session-pooler connection string in `SUPABASE_DATABASE_URL`. For extraction, choose one provider:

```text
TERNFOLD_AI_PROVIDER=openrouter
OPENROUTER_API_KEY=...
```

or:

```text
TERNFOLD_AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
```

or NVIDIA NIM's OpenAI-compatible endpoint:

```text
TERNFOLD_AI_PROVIDER=nvidia
NVIDIA_API_KEY=...
NVIDIA_MODEL=deepseek-ai/deepseek-v4-pro-0813
```

Use `.\ternfold-supabase.ps1 Setup` and `.\ternfold-supabase.ps1 Start` after the connection string is present. The ordinary `ternfold.ps1` launcher keeps using isolated local PostgreSQL for offline demonstrations.

The core workflow and deterministic calculations do not need an AI key. PDF/image values can always be entered beside their source; CSV input creates unconfirmed proposals. Live model output is saved only as a draft and never confirms applicability or calculates contribution.

See [OPERATIONS.md](OPERATIONS.md) for setup, retention and pilot boundaries, and [REQUIREMENTS_VERIFICATION.md](REQUIREMENTS_VERIFICATION.md) for the release evidence.

