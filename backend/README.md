# WCM Sales Assistant API

Auth is live. Other extension routes return `503 upstream_error` until implemented.
The app applies pending SQL migrations on startup when `DATABASE_URL` is set.

```bash
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check app tests
uv run mypy app
```

Use the same Supabase project, Postgres database, and `ENCRYPTION_KEY` as the AI Lead Pipeline. The backend reads `public.profiles`; it never writes that table. Grant `chrome_extension` through the AI Lead Pipeline Access Control screen.

App data stays in the separate `extension` schema. Applied filenames are recorded in `extension.schema_migrations`; concurrent instances serialize migration runs with a Postgres advisory lock. Roll back application code without dropping the schema or its data. Database changes need a new forward migration.

`orjson` handles provider JSON and non-model API responses. Auth responses with Pydantic models use FastAPI's built-in serializer.

Point the extension's `WXT_API_BASE_URL` to this server and set `WXT_API_MOCK=false`. Real-account 2FA login requires valid Supabase credentials and cannot run in offline tests.
