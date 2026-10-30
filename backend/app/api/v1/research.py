import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import asyncpg
import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.dependencies import get_http_client, require_extension_access
from app.core.exceptions import AppError
from app.core.json import OrjsonResponse
from app.models.user import UserProfile
from app.repositories.audit_repository import AuditRepository, to_wire
from app.services import ghl, site_ai, site_audit, site_crawl, site_score

logger = logging.getLogger(__name__)
router = APIRouter(tags=["research"])

# Everything site_audit.analyze fills from the home page; the rest needs provider keys.
INITIAL_STATE = {k: "pending" for k in site_audit.SECTION_KEYS}
# ponytail: in-process jobs, max 3 at once, single instance. Move to a queue if scaled out.
_sem = asyncio.Semaphore(3)
_tasks: set[asyncio.Task[None]] = set()
# After the other steps finish, wait at most this long for PageSpeed before scoring.
PAGESPEED_WAIT_S = 60.0


def _repo(request: Request) -> AuditRepository:
    pool: asyncpg.Pool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise AppError(503, "upstream_error", "Database is not configured")
    return AuditRepository(pool)


def _digits(value: object) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())[-10:]


def _domain(host: str) -> str:
    return host.lower().rstrip(".").removeprefix("www.")


LABELS = {
    "home": "Fetch home page",
    "analyze": "Analyse home page",
    "map": "Find pages",
    "pick": "Choose pages to read",
    "scrape": "Read pages",
    "enrich": "Build site facts",
    "ai": "AI page analysis",
    "gbp": "Google Business Profile",
    "psi": "PageSpeed",
    "score": "Score the audit",
    "final": "Audit finished",
}


def _why(exc: Exception) -> str:
    """Short failure text for the trace. Never str(exc): httpx errors carry the URL, key included."""
    if isinstance(exc, AppError):
        return exc.message
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


class _Trace:
    """Writes the step-by-step run log shown in the panel. A write problem never touches the audit."""

    def __init__(self, repo: AuditRepository, audit_id: str) -> None:
        self._repo, self._id = repo, audit_id
        self._started: dict[str, float] = {}
        self._open: set[str] = set()

    async def report(self, step: str, status: str, **detail: Any) -> None:
        now = time.monotonic()
        ms = detail.pop("ms", None)
        if status == "running":
            self._started[step] = now
            self._open.add(step)
        else:
            self._open.discard(step)
            if ms is None and step in self._started:
                ms = round((now - self._started.pop(step)) * 1000)
        event = {
            "id": step,
            "status": status,
            "label": LABELS.get(step)
            or urlsplit(step.removeprefix("page:")).path
            or "/",
            "ms": ms,
            "at": datetime.now(UTC).isoformat(),
            "detail": detail,
        }
        try:
            async with asyncio.timeout(2):
                await self._repo.add_trace(self._id, event)
        except Exception:
            logger.warning("audit %s: trace write failed", self._id, exc_info=True)

    async def skip(self, reason: str, *steps: str) -> None:
        for step in steps:
            await self.report(step, "skipped", reason=reason)

    async def fail_open(self, error: str) -> None:
        for step in list(self._open):
            await self.report(step, "failed", error=error)


async def _home(
    http: httpx.AsyncClient, url: str, hints: dict[str, str], trace: _Trace
) -> tuple[dict[str, Any], str, str, str]:
    """Returns (sections, final URL, home HTML, via): via is "firecrawl" when the site
    blocked the direct fetch, so the crawl reads every other page through Firecrawl too."""
    await trace.report("home", "running")
    via, reason = "direct", None
    try:
        html, final_url = await site_audit.fetch_html(url)
    except AppError as exc:
        if not settings.FIRECRAWL_API_KEY:
            raise
        # Sites behind a WAF or rendered by JavaScript: let Firecrawl fetch them.
        fallback = await site_crawl.scrape(http, url)
        if not fallback:
            raise
        html, final_url = fallback, url
        via, reason = "firecrawl", exc.message
    await trace.report(
        "home", "done", via=via, reason=reason, url=final_url, size=len(html)
    )
    await trace.report("analyze", "running")
    sections = site_audit.analyze(html, final_url, hints)
    await trace.report("analyze", "done")
    return sections, final_url, html, via


async def _enrich(
    repo: AuditRepository,
    http: httpx.AsyncClient,
    audit_id: str,
    sections: dict[str, Any],
    final_url: str,
    home_html: str,
    via: str,
    hints: dict[str, str],
    trace: _Trace,
) -> bool:
    """Add whole-site, AI and GBP data. Returns False if a provider step failed."""
    ok = True
    pages = {final_url: home_html}
    # Runs without a Firecrawl key too: the home page menu and links are enough to start.
    try:
        urls, crawled, crawl_ok, sitemap = await site_crawl.crawl(
            http, final_url, home_html, via, trace.report
        )
        ok = crawl_ok  # False when the site map failed; the menu-based crawl still ran
        await trace.report("enrich", "running")
        posts = await site_crawl.blog_posts(http, urls, crawled, final_url, sitemap)
        menu = site_crawl.nav_links(home_html, final_url)
        site_crawl.enrich(sections, urls, crawled, posts, menu)
        await trace.report(
            "enrich",
            "done",
            pages=len(crawled) + 1,
            posts=sections["site"]["blog"]["post_count"],
        )
        pages |= crawled
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("audit %s: site crawl failed", audit_id, exc_info=True)
        await trace.fail_open(_why(exc))
        ok = False  # home-page site/convert data is kept
    if settings.OPENROUTER_API_KEY:
        await trace.report("ai", "running")
        try:
            site_ai.apply(sections, await site_ai.analyze(http, pages), pages)
            await trace.report("ai", "done", pages=len(pages))
        except (AppError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("audit %s: AI page analysis failed", audit_id, exc_info=True)
            await trace.report("ai", "failed", error=_why(exc))
            ok = False  # keyword results are kept
    else:
        await trace.skip("OpenRouter key not set", "ai")
    await repo.update(
        audit_id,
        sections={"site": sections["site"], "convert": sections["convert"]},
        state={"site": "ready", "convert": "ready"},
    )
    if settings.APIFY_API_TOKEN and settings.APIFY_GMAPS_ACTOR_ID:
        domain = _domain(urlsplit(final_url).hostname or "")
        await trace.report("gbp", "running")
        try:
            gbp, tried = await site_crawl.gbp_lookup(
                http,
                site_crawl.gbp_queries(hints, home_html, domain),
                domain,
                sections["business"]["nap"].get("phone"),
            )
            if gbp:
                gbp["website_links_to_gbp"], gbp["review_link_on_site"] = (
                    site_crawl.gbp_links(pages)
                )
                business = sections["business"]
                business["gbp"] = gbp
                nap = business["nap"]
                site_phone, gbp_phone = (
                    _digits(nap.get("phone")),
                    _digits(gbp.get("phone")),
                )
                if len(site_phone) == 10 and len(gbp_phone) == 10:  # else unknown
                    nap["consistent_with_gbp"] = site_phone == gbp_phone
                # The profile was found by its website address; the phone is a second proof.
                gbp["match_reasons"] = [
                    "website address",
                    *(
                        ["phone number"]
                        if nap.get("consistent_with_gbp") is True
                        else []
                    ),
                ]
            await trace.report("gbp", "done", matched=bool(gbp), searches=len(tried))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("audit %s: GBP lookup failed", audit_id, exc_info=True)
            await trace.report("gbp", "failed", error=_why(exc))
            ok = False
        await repo.update(
            audit_id,
            sections={"business": sections["business"]},
            state={"business": "ready"},
        )
    else:
        await trace.skip("Apify token not set", "gbp")
    return ok


async def _pagespeed(
    repo: AuditRepository,
    http: httpx.AsyncClient,
    audit_id: str,
    sections: dict[str, Any],
    final_url: str,
    trace: _Trace,
) -> bool:
    """Fill on_page.pagespeed. Runs next to _enrich so the slow PSI call blocks nothing."""
    ok = True
    await trace.report("psi", "running")
    try:
        sections["on_page"]["pagespeed"] = await site_crawl.pagespeed(http, final_url)
        psi = sections["on_page"]["pagespeed"]
        await trace.report(
            "psi",
            "done",
            mobile=psi.get("mobile_performance"),
            desktop=(psi.get("desktop") or {}).get("performance"),
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        # no exc_info: the traceback text carries the request URL, API key included
        logger.warning("audit %s: PageSpeed lookup failed: %s", audit_id, _why(exc))
        await trace.report("psi", "failed", error=_why(exc))
        ok = False  # pagespeed stays None
    await repo.update(
        audit_id, sections={"on_page": sections["on_page"]}, state={"on_page": "ready"}
    )
    return ok


async def _run(
    repo: AuditRepository,
    http: httpx.AsyncClient,
    audit_id: str,
    url: str,
    hints: dict[str, str],
) -> None:
    trace = _Trace(repo, audit_id)
    async with _sem:
        await repo.update(
            audit_id, status="running", state={k: "running" for k in INITIAL_STATE}
        )
        speed: asyncio.Task[bool] | None = None
        try:
            sections, final_url, home_html, via = await _home(http, url, hints, trace)
            # scored once every step below has finished; the crawl always runs
            later = {"overview", "site", "convert"}
            if settings.APIFY_API_TOKEN and settings.APIFY_GMAPS_ACTOR_ID:
                later.add("business")
            if settings.GOOGLE_PAGESPEED_API_KEY:
                later.add("on_page")
            # Home-page results show right away; crawl and GBP sections fill in after.
            await repo.update(
                audit_id,
                sections=sections,
                state={k: "running" if k in later else "ready" for k in INITIAL_STATE},
            )
            if settings.GOOGLE_PAGESPEED_API_KEY:
                speed = asyncio.create_task(
                    _pagespeed(repo, http, audit_id, sections, final_url, trace)
                )
            else:
                await trace.skip("PageSpeed key not set", "psi")
            ok = await _enrich(
                repo, http, audit_id, sections, final_url, home_html, via, hints, trace
            )
            psi_ok: bool | None = None  # None: PageSpeed not run (no key)
            if speed:
                try:
                    psi_ok = await asyncio.wait_for(speed, PAGESPEED_WAIT_S)
                except TimeoutError:  # wait_for has cancelled the task
                    psi_ok = False
                    logger.warning("audit %s: PageSpeed timed out", audit_id)
                    await trace.report("psi", "failed", error="Timed out")
                    await repo.update(audit_id, state={"on_page": "ready"})
                ok = bool(psi_ok) and ok
            await trace.report("score", "running")
            overview = site_score.compute(
                sections,
                pagespeed_ok=psi_ok,
                domain=_domain(urlsplit(final_url).hostname or ""),
            )
            await repo.update(
                audit_id, sections={"overview": overview}, state={"overview": "ready"}
            )
            await trace.report(
                "score", "done", score=overview["score"], grade=overview["grade"]
            )
        except AppError as exc:
            await trace.fail_open(exc.message)
            await trace.report("final", "failed", outcome="failed", error=exc.message)
            await repo.update(
                audit_id,
                status="failed",
                error=exc.message,
                finished=True,
                state={k: "failed" for k in INITIAL_STATE},
            )
            return
        except Exception:  # never leave an audit stuck in `running`
            logger.exception("audit %s crashed", audit_id)
            await trace.fail_open("Unexpected error")
            await trace.report("final", "failed", outcome="failed")
            await repo.update(
                audit_id,
                status="failed",
                error="Audit failed unexpectedly",
                finished=True,
                state={k: "failed" for k in INITIAL_STATE},
            )
            return
        finally:
            if speed and not speed.done():
                speed.cancel()
        await trace.report("final", "done", outcome="ready" if ok else "partial")
        await repo.update(audit_id, status="ready" if ok else "partial", finished=True)


async def _start(
    repo: AuditRepository,
    http: httpx.AsyncClient,
    user_id: str,
    raw_url: str,
    force: bool,
    hints: dict[str, str],
) -> tuple[asyncpg.Record, bool]:
    """Return (audit row, created). Reuses a fresh audit for the domain unless forced."""
    url, host = site_audit.normalize_url(raw_url)
    domain = _domain(host)
    if not force and (fresh := await repo.latest(domain, fresh_only=True)):
        return fresh, False
    row = await repo.create(user_id, url, domain, INITIAL_STATE)
    task = asyncio.create_task(_run(repo, http, str(row["id"]), url, hints))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return row, True


async def _audit(repo: AuditRepository, audit_id: str) -> asyncpg.Record:
    row = await repo.get(audit_id)
    if row is None:
        raise AppError(404, "audit_not_found", "Audit not found")
    return row


class StartAudit(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    force: bool = False


@router.post("/research/audits")
async def start_audit(
    body: StartAudit,
    request: Request,
    profile: UserProfile = Depends(require_extension_access),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> Response:
    row, created = await _start(
        _repo(request), http, profile.id, body.url, body.force, {}
    )
    return OrjsonResponse(to_wire(row), status_code=202 if created else 200)


@router.get("/research/audits/latest", dependencies=[Depends(require_extension_access)])
async def latest_audit(domain: str, request: Request) -> dict[str, Any]:
    # Any tab domain can be asked for (localhost, google.com, ...); unknown means not found.
    row = await _repo(request).latest(_domain(domain))
    if row is None:
        raise AppError(404, "audit_not_found", "No audit for this domain yet")
    return to_wire(row)


@router.get(
    "/research/audits/{audit_id}", dependencies=[Depends(require_extension_access)]
)
async def get_audit(audit_id: str, request: Request) -> dict[str, Any]:
    return to_wire(await _audit(_repo(request), audit_id))


class LocalCompetitorsRequest(BaseModel):
    query: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _apify_places(
    http: httpx.AsyncClient, query: str, location: str
) -> list[dict[str, Any]]:
    r = await http.post(
        f"https://api.apify.com/v2/acts/{settings.APIFY_GMAPS_ACTOR_ID}/run-sync-get-dataset-items",
        params={"token": settings.APIFY_API_TOKEN},
        json={
            "searchStringsArray": [query],
            "locationQuery": location,
            "maxCrawledPlacesPerSearch": 20,
            "language": "en",
        },
        timeout=90,
    )
    if r.status_code >= 400:
        raise AppError(
            502, "upstream_error", f"Competitor search failed ({r.status_code})"
        )
    items = r.json()
    return items if isinstance(items, list) else []


@router.post(
    "/research/audits/{audit_id}/local-competitors",
    dependencies=[Depends(require_extension_access)],
)
async def local_competitors(
    audit_id: str,
    body: LocalCompetitorsRequest,
    request: Request,
    http: httpx.AsyncClient = Depends(get_http_client),
) -> dict[str, Any]:
    repo = _repo(request)
    audit = to_wire(await _audit(repo, audit_id))
    research = audit.get("research") or site_audit.empty_research()
    services = ((audit.get("site") or {}).get("services") or {}).get("clusters") or []
    query = (body.query or (services[0]["service"] if services else "med spa")).strip()
    location = (body.location or "").strip()
    if not settings.APIFY_API_TOKEN or not settings.APIFY_GMAPS_ACTOR_ID:
        result: dict[str, Any] = {
            "state": "failed",
            "data": None,
            "ran_at": _now(),
            "error": "Local competitor search is not set up yet (APIFY_API_TOKEN).",
        }
    elif not location:
        result = {
            "state": "failed",
            "data": None,
            "ran_at": _now(),
            "error": "Enter a city or area to search near.",
        }
    else:
        try:
            places = await _apify_places(http, query, location)
            items = []
            for rank, p in enumerate(places[:20], 1):
                site = p.get("website") or None
                host = _domain(urlsplit(site).hostname or "") if site else ""
                items.append(
                    {
                        "rank": rank,
                        "name": str(p.get("title") or ""),
                        "rating": p.get("totalScore"),
                        "review_count": p.get("reviewsCount"),
                        "website": site,
                        "is_this_business": bool(host) and host == audit["domain"],
                    }
                )
            result = {
                "state": "ready",
                "error": None,
                "ran_at": _now(),
                "data": {"query": query, "location": location, "items": items},
            }
        except (AppError, httpx.HTTPError, ValueError) as exc:
            message = (
                exc.message if isinstance(exc, AppError) else "Competitor search failed"
            )
            result = {
                "state": "failed",
                "data": None,
                "error": message,
                "ran_at": _now(),
            }
    research = {**research, "local_competitors": result}
    await repo.update(audit_id, sections={"research": research})
    return to_wire(await _audit(repo, audit_id))


@router.get("/research/audits/{audit_id}/report")
async def report(
    audit_id: str,
    request: Request,
    profile: UserProfile = Depends(require_extension_access),
) -> dict[str, Any]:
    audit = to_wire(await _audit(_repo(request), audit_id))
    nap = (audit.get("business") or {}).get("nap") or {}
    overview = audit.get("overview") or {}
    prepared_for = nap.get("name") or audit["domain"]
    intro = f"This report reviews {audit['domain']} the way a prospective patient and Google see it."
    if overview.get("score") is not None:
        intro += (
            f" It scores {overview['score']}/100 ({overview.get('grade')}),"
            f" with {overview.get('issue_count', 0)} items to fix."
        )
    return {
        "audit": audit,
        "prepared_for": prepared_for,
        "prepared_by": f"WCM · {profile.full_name or profile.email}",
        "generated_at": _now(),
        "intro": intro,
    }


class StartContactResearch(BaseModel):
    force: bool = False


async def _contact_site(
    http: httpx.AsyncClient, contact_id: str
) -> tuple[dict[str, Any], str | None]:
    contact = await ghl.get_contact(http, contact_id)  # location guard
    return contact, await ghl.contact_website(http, contact)


@router.get(
    "/contacts/{contact_id}/research", dependencies=[Depends(require_extension_access)]
)
async def contact_research(
    contact_id: str,
    request: Request,
    http: httpx.AsyncClient = Depends(get_http_client),
) -> dict[str, Any]:
    _, website = await _contact_site(http, contact_id)
    if not website:
        return {"audit": None, "reason": "no_website"}
    _, host = site_audit.normalize_url(website)
    row = await _repo(request).latest(_domain(host))
    return {"audit": to_wire(row) if row else None}


@router.post("/contacts/{contact_id}/research")
async def start_contact_research(
    contact_id: str,
    request: Request,
    body: StartContactResearch | None = None,
    profile: UserProfile = Depends(require_extension_access),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> dict[str, Any]:
    contact, website = await _contact_site(http, contact_id)
    if not website:
        return {"audit": None, "reason": "no_website"}
    hints = (
        {"name": contact.get("companyName") or ""} if contact.get("companyName") else {}
    )
    row, _ = await _start(
        _repo(request), http, profile.id, website, bool(body and body.force), hints
    )
    return {"audit": to_wire(row)}
