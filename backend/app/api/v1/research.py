"""HTTP routes for audits, local competitors, the AI visibility report and contact research.
Each route checks access, reads the request and calls a service; the logic is in app/services."""

from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.core.dependencies import (
    get_audit_repo,
    get_http_client,
    require_extension_access,
)
from app.core.exceptions import AppError
from app.core.json import OrjsonResponse
from app.models.user import UserProfile
from app.repositories.audit_repository import to_wire
from app.schemas.research import (
    AiFullRequest,
    LocalCompetitorsRequest,
    StartAudit,
    StartContactResearch,
)
from app.services import (
    ai_runs,
    audit_runner,
    contact_research,
    local_competitors,
    report,
)

router = APIRouter(tags=["research"])


@router.post("/research/audits")
async def start_audit(
    body: StartAudit,
    request: Request,
    profile: UserProfile = Depends(require_extension_access),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> Response:
    row, created = await audit_runner.start(
        get_audit_repo(request), http, profile.id, body.url, body.force, {}
    )
    return OrjsonResponse(to_wire(row), status_code=202 if created else 200)


@router.get("/research/audits/latest", dependencies=[Depends(require_extension_access)])
async def latest_audit(domain: str, request: Request) -> dict[str, Any]:
    # Any tab domain can be asked for (localhost, google.com, ...); unknown means not found.
    row = await get_audit_repo(request).latest(audit_runner.domain_of(domain))
    if row is None:
        raise AppError(404, "audit_not_found", "No audit for this domain yet")
    return to_wire(row)


@router.get(
    "/research/audits/{audit_id}", dependencies=[Depends(require_extension_access)]
)
async def get_audit(audit_id: str, request: Request) -> dict[str, Any]:
    return to_wire(await audit_runner.fetch_audit(get_audit_repo(request), audit_id))


@router.post(
    "/research/audits/{audit_id}/local-competitors",
    dependencies=[Depends(require_extension_access)],
)
async def local_competitors_search(
    audit_id: str,
    body: LocalCompetitorsRequest,
    request: Request,
    http: httpx.AsyncClient = Depends(get_http_client),
) -> dict[str, Any]:
    return await local_competitors.search(
        get_audit_repo(request), http, audit_id, body.query, body.location
    )


@router.post("/research/audits/{audit_id}/ai-visibility/questions")
async def ai_questions(
    audit_id: str,
    request: Request,
    profile: UserProfile = Depends(require_extension_access),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> dict[str, Any]:
    return await ai_runs.suggest_questions(
        get_audit_repo(request), http, audit_id, profile
    )


@router.post("/research/audits/{audit_id}/ai-visibility/full")
async def start_ai_report(
    audit_id: str,
    body: AiFullRequest,
    request: Request,
    profile: UserProfile = Depends(require_extension_access),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> Response:
    audit = await ai_runs.start_report(
        get_audit_repo(request),
        http,
        audit_id,
        profile,
        body.prompts,
        body.n_prompts,
        body.runs,
    )
    return OrjsonResponse(audit, status_code=202)


@router.get("/research/ai-visibility/runs/{run_id}/answers")
async def ai_run_answers(
    run_id: str,
    request: Request,
    engine: str | None = None,
    prompt: int | None = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    _: UserProfile = Depends(require_extension_access),
) -> dict[str, Any]:
    return await ai_runs.answers_page(
        get_audit_repo(request),
        run_id,
        engine=engine,
        prompt=prompt,
        limit=limit,
        offset=offset,
    )


@router.get("/research/audits/{audit_id}/report")
async def audit_report(
    audit_id: str,
    request: Request,
    profile: UserProfile = Depends(require_extension_access),
) -> dict[str, Any]:
    audit = to_wire(await audit_runner.fetch_audit(get_audit_repo(request), audit_id))
    return report.build(audit, profile)


@router.get(
    "/contacts/{contact_id}/research", dependencies=[Depends(require_extension_access)]
)
async def contact_research_latest(
    contact_id: str,
    request: Request,
    http: httpx.AsyncClient = Depends(get_http_client),
) -> dict[str, Any]:
    return await contact_research.latest(
        lambda: get_audit_repo(request), http, contact_id
    )


@router.post("/contacts/{contact_id}/research")
async def start_contact_research(
    contact_id: str,
    request: Request,
    body: StartContactResearch | None = None,
    profile: UserProfile = Depends(require_extension_access),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> dict[str, Any]:
    return await contact_research.start(
        lambda: get_audit_repo(request),
        http,
        profile.id,
        contact_id,
        bool(body and body.force),
    )
