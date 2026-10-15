import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import asyncpg
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, stubs
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.rate_limit import prune


async def prune_rate_limits() -> None:
    while True:
        await asyncio.sleep(300)
        prune(60)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pool = (
        await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=1,
            max_size=5,
            statement_cache_size=0,
        )
        if settings.DATABASE_URL
        else None
    )
    async with httpx.AsyncClient(timeout=10) as client:
        app.state.http_client = client
        prune_task = asyncio.create_task(prune_rate_limits())
        try:
            yield
        finally:
            prune_task.cancel()
            with suppress(asyncio.CancelledError):
                await prune_task
            if app.state.pool is not None:
                await app.state.pool.close()


app = FastAPI(title="WCM Sales Assistant API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        s.strip() for s in settings.CORS_ALLOWED_ORIGINS.split(",") if s.strip()
    ],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)
register_exception_handlers(app)


@app.middleware("http")
async def request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    response.headers["X-Request-Id"] = str(uuid.uuid4())
    return response


@app.get("/health")
async def health(request: Request) -> dict[str, object]:
    missing = [
        key
        for key in (
            "DATABASE_URL",
            "SUPABASE_URL",
            "SUPABASE_PUBLISHABLE_KEY",
            "ENCRYPTION_KEY",
        )
        if not getattr(settings, key)
    ]
    pool: asyncpg.Pool | None = getattr(request.app.state, "pool", None)
    db = False
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db = True
        except (asyncpg.PostgresError, OSError):
            db = False
    return {"db": db, "missing_config": missing}


app.include_router(auth.router, prefix="/api/v1/ext")
app.include_router(stubs.router, prefix="/api/v1/ext")
app.include_router(stubs.webhook_router)
