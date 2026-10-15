# WCM Sales Assistant API

Auth is live. Other extension routes return `503 upstream_error` until implemented.

```bash
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check app tests
uv run mypy app
```

Use the same Supabase project, Postgres database, and `ENCRYPTION_KEY` as the AI Lead Pipeline. The backend reads `public.profiles`; it never writes that table. Grant `chrome_extension` through the AI Lead Pipeline Access Control screen.

Point the extension's `WXT_API_BASE_URL` to this server and set `WXT_API_MOCK=false`. Real-account 2FA login requires valid Supabase credentials and cannot run in offline tests.
