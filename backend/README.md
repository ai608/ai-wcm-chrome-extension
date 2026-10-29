# WCM Sales Assistant API

Auth is live. Other extension routes return `503 upstream_error` until implemented.
The app applies pending SQL migrations on startup when `DATABASE_URL` is set.

```bash
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --port 8001
uv run pytest
uv run ruff check app tests
uv run mypy app
```

Use the same Supabase project, Postgres database, and `ENCRYPTION_KEY` as the AI Lead Pipeline. The backend reads `public.profiles`; it never writes that table. Grant `chrome_extension` through the AI Lead Pipeline Access Control screen.

Use the Supabase transaction pooler on port 6543 for `DATABASE_URL`. Configure pool size, overflow, acquire timeout, command timeout, and idle lifetime with the `DB_*` settings in `.env.example`. Set `CORS_ALLOWED_ORIGINS` to the extension's `chrome-extension://` origin. For local builds whose IDs change, `CORS_ALLOWED_ORIGIN_REGEX=^chrome-extension://[a-p]{32}$` permits extension origins during development.

App data stays in the separate `extension` schema. Applied filenames are recorded in `extension.schema_migrations`; concurrent instances serialize migration runs with a Postgres advisory lock. Roll back application code without dropping the schema or its data. Database changes need a new forward migration.

`orjson` handles provider JSON and non-model API responses. Auth responses with Pydantic models use FastAPI's built-in serializer.

Set the same `EXTENSION_HANDOFF_SECRET` in this backend and the AI Lead Pipeline backend. Add the installed extension ID to `EXTENSION_ALLOWED_IDS` in both. O1 runs on port 8000 and the O1 frontend runs on port 5173 locally. Point `WXT_API_BASE_URL` at this server on port 8001, set `WXT_O1_WEB_URL` to the O1 frontend, and set `WXT_API_MOCK=false`.

The extension opens O1 for sign-in. O1 issues a one-time code after checking the user's grant. This backend exchanges the code for an extension session. The migration creates `extension.auth_sessions`; tokens are stored as hashes. Existing password endpoints remain for compatibility during rollout.

## Deploy on Railway

1. New project → deploy from this repo, set **Root Directory** to `backend` (picks up `Dockerfile` and `railway.json`).
2. Add the variables from `.env.example` (at minimum `ENV=production`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `ENCRYPTION_KEY`, `EXTENSION_HANDOFF_SECRET`, `EXTENSION_ALLOWED_IDS`, `CORS_ALLOWED_ORIGINS`). Railway sets `PORT` itself.
3. Generate a public domain. Migrations run on boot; `/health` is the healthcheck and lists any `missing_config`.

Local: `docker compose up --build` from the repo root (reads `backend/.env`).
