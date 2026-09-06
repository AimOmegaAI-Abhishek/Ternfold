# Supabase operations and pilot boundaries

## Setup and recovery

- Ternfold requires `SUPABASE_DATABASE_URL`; it has no local database fallback.
- Run `.\ternfold.ps1 Setup` to apply migrations and seed the synthetic demo, then `.\ternfold.ps1 Start`.
- `Status` reports the web process and confirms the Supabase-only database profile.
- If startup fails, inspect `%LOCALAPPDATA%\Ternfold\logs\web-error.log`.
- `Reset-Demo` refuses to run if any non-synthetic organization exists. Never use it against a customer database.

## Data and retention

Supabase PostgreSQL stores all application records. During a local web run, synthetic evidence and reports remain under `%LOCALAPPDATA%\Ternfold\storage`. A Vercel or external pilot must use a private Supabase Storage bucket because serverless local files are temporary.

An organization owner can close a decided service case in Settings. Run `.\ternfold.ps1 Apply-Retention` as the scheduled operating action. It removes source bytes 30 days after closure and case records/reports 90 days after closure, leaving an organization-level deletion receipt. External backups must expire within 30 additional days and reapply the deletion ledger after restore.

## Configuration

Secrets belong in `%LOCALAPPDATA%\Ternfold\.env` for the local web process and in the hosting provider's encrypted environment-variable settings for deployment.

- `SUPABASE_DATABASE_URL`: Session pooler PostgreSQL URI including the database password.
- `TERNFOLD_AI_PROVIDER=nvidia` plus `NVIDIA_API_KEY`, or the documented OpenRouter/Anthropic alternatives.
- `TERNFOLD_SECURE_COOKIES=1` whenever HTTPS is used.

Live extraction sends machine-readable PDF or CSV text to the selected provider. It records a source-linked draft, never a confirmed input. Provider errors preserve the source and return the reviewer to manual entry.

## External pilot gates

Before real data is accepted, complete private Supabase Storage integration, India-region deployment checks, HTTPS, invitation/reset delivery, encrypted backup and clean-restore tests, scheduled retention, customer processing terms, reviewer/support ownership, and a deployed P0 rerun. Live AI additionally requires customer permission and a provider arrangement compatible with the agreed India data requirement.
