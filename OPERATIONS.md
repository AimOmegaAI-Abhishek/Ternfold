# Local operations and pilot boundaries

## Setup and recovery

- Run `.\ternfold.ps1 Setup` once, then `.\ternfold.ps1 Start` whenever the demo is needed.
- `Status` reports the web and isolated PostgreSQL processes. `Stop` stops only Ternfold’s local processes.
- If startup fails, inspect `%LOCALAPPDATA%\Ternfold\logs\web-error.log` and `postgres.log`. Running `Setup` again is safe: migrations and synthetic seeding are idempotent.
- `Reset-Demo` checks every organization first. It refuses the reset if any non-synthetic organization exists. This is the safe sales-demo reset and must never be repointed at a customer database.
- `Test` starts PostgreSQL when needed, then uses `ternfold_test` and workspace test storage. It does not modify the demonstration database.

## Data and retention

Local source files and generated reports live under `%LOCALAPPDATA%\Ternfold\storage`; PostgreSQL data lives under `%LOCALAPPDATA%\Ternfold\postgres`. Customer files do not belong in the source folder.

An organization owner can close a decided service case in Settings. Run `.\ternfold.ps1 Apply-Retention` as the scheduled operating action. It deletes source bytes 30 days after closure and case records/reports 90 days after closure, leaving an organization-level deletion receipt. External backups must expire within 30 additional days and must reapply the deletion ledger after restore.

Before real data is accepted, test encrypted backups and a clean restore in the chosen India region. The local demo does not constitute that test.

## Supabase and model configuration

Secrets belong only in `%LOCALAPPDATA%\Ternfold\.env`, outside the OneDrive source folder. The local `Setup` command creates the file from `.env.example`; then set:

- `SUPABASE_DATABASE_URL`: the exact session-pooler PostgreSQL URI from Supabase **Connect**, including the project password.
- `TERNFOLD_AI_PROVIDER=openrouter` plus `OPENROUTER_API_KEY`, or `TERNFOLD_AI_PROVIDER=anthropic` plus `ANTHROPIC_API_KEY`.
- Optionally change the documented model name. Restart after any `.env` change.

The ordinary launcher deliberately uses isolated local PostgreSQL. After the connection string is configured, `.\ternfold-supabase.ps1 Setup` applies migrations and seeds the synthetic demo, and `.\ternfold-supabase.ps1 Start` runs the same application against Supabase. External use still needs separate pilot authorization.

Live extraction sends machine-readable PDF or CSV text to the selected provider. It records a source-linked draft, never a confirmed input. Images and scanned PDFs stay on the manual path unless an approved OCR provider is added. Provider errors preserve the source and return the reviewer to manual entry.

## External pilot gates

The local MVP is not an external deployment. An assisted pilot still requires: a founder-approved Supabase/hosting/storage quote; an India-region deployment and private object store; HTTPS and secure cookies; invitation and password-reset delivery; encrypted backup/restore evidence; scheduled retention; customer processing/retention terms; named reviewer/support ownership; and a complete deployed P0 rerun. Live AI additionally requires a provider key, customer permission and confirmation that the provider arrangement satisfies the India data requirement.

