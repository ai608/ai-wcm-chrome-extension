import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import asyncpg
import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.dependencies import get_http_client, require_extension_access
from app.core.exceptions import AppError
from app.core.json import OrjsonResponse
from app.core.rate_limit import rate_limit
from app.models.user import UserProfile
from app.repositories.audit_repository import AuditRepository, to_wire
from app.services import (
    ai_report,
    ai_visibility,
    crawl_access,
    fetchlog,
    ghl,
    onpage,
    probes,
    site_ai,
    site_audit,
    site_crawl,
    site_score,
    usage,
)

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
    "probe": "Check links and redirects",
    "onpage": "Check every page",
    "ai": "AI page analysis",
    "gbp": "Google Business Profile",
    "psi": "PageSpeed",
    "score": "Score the audit",
    "usage": "Cost and tokens",
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
        if site_crawl._blocked(html):
            # HTTP 200 with a bot-protection page: not the home page. Treat it like a failed read
            # so Firecrawl gets a turn, and never audit the wall as if it were the clinic's site.
            raise AppError(
                422,
                "site_blocked",
                "The website's bot protection blocked our reader. Try again later.",
            )
    except AppError as exc:
        if not settings.FIRECRAWL_API_KEY:
            raise
        # Sites behind a WAF or rendered by JavaScript: let Firecrawl fetch them.
        fallback = await site_crawl.scrape(http, url)
        if not fallback or site_crawl._blocked(fallback):
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
    urls: list[str] = []
    menu = site_crawl.nav_links(home_html, final_url)
    try:
        urls, crawled, crawl_ok, sitemap = await site_crawl.crawl(
            http, final_url, home_html, via, trace.report, menu
        )
        ok = crawl_ok  # False when the site map failed; the menu-based crawl still ran
        await trace.report("enrich", "running")
        posts = await site_crawl.blog_posts(http, urls, crawled, final_url, sitemap)
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
    probe_data: dict[str, Any] = {}
    if via != "direct":
        # A site that only answers through Firecrawl blocks direct requests: a "broken link"
        # verdict from one of ours would be false.
        await trace.skip("The site blocks direct requests", "probe")
    else:
        await trace.report("probe", "running")
        try:
            probe_data = await probes.run(
                home=final_url, home_html=home_html, pages=pages
            )
            await trace.report(
                "probe",
                "done",
                checked=probe_data["checked"],
                timed_out=probe_data["timed_out"],
            )
        except (AppError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("audit %s: link checks failed", audit_id, exc_info=True)
            await trace.report("probe", "failed", error=_why(exc))
    await trace.report("onpage", "running")
    try:
        try:
            access = await asyncio.wait_for(
                crawl_access.load(final_url), settings.CRAWL_SITEMAP_WAIT_S
            )
        except TimeoutError:
            access = None
        onpage.run(
            sections,
            final_url,
            pages,
            urls,
            menu,
            access,
            fetched=fetchlog.snapshot(),
            probes=probe_data,
        )
        summary = sections["on_page"]["summary"]
        await trace.report(
            "onpage",
            "done",
            pages=len(pages),
            score=summary["score"],
            critical=summary["critical"],
            high=summary["high"],
        )
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        logger.warning("audit %s: on-page checks failed", audit_id, exc_info=True)
        await trace.report("onpage", "failed", error=_why(exc))
        ok = False
    if settings.OPENROUTER_API_KEY:
        await trace.report("ai", "running")
        try:
            names = [c["service"] for c in sections["site"]["services"]["clusters"]]
            site_ai.apply(sections, await site_ai.analyze(http, pages, names), pages)
            await trace.report("ai", "done", pages=len(pages))
        except (AppError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("audit %s: AI page analysis failed", audit_id, exc_info=True)
            await trace.report("ai", "failed", error=_why(exc))
            ok = False  # keyword results are kept
    else:
        await trace.skip("OpenRouter key not set", "ai")
    await repo.update(
        audit_id,
        sections={
            "site": sections["site"],
            "convert": sections["convert"],
            "on_page": sections["on_page"],
            "schema": sections["schema"],
        },
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


async def _report_usage(
    trace: _Trace, meter: usage.Meter, repo: AuditRepository, audit_id: str
) -> None:
    """The "Cost and tokens" step, just before the final step, and the AI spend saved on the audit
    row for the Settings total. Nothing spent: no step. A write problem never touches the audit."""
    if meter.empty():
        return
    await trace.report("usage", "done", **meter.snapshot())
    cost, tokens = meter.ai_totals()
    if cost or tokens:
        try:
            async with asyncio.timeout(2):
                await repo.set_audit_spend(audit_id, cost, tokens)
        except Exception:
            logger.warning("audit %s: saving AI spend failed", audit_id, exc_info=True)


async def _run(
    repo: AuditRepository,
    http: httpx.AsyncClient,
    audit_id: str,
    url: str,
    hints: dict[str, str],
) -> None:
    trace = _Trace(repo, audit_id)
    async with _sem:
        meter = (
            usage.bind()
        )  # counts what this audit spends; shown as "Cost and tokens"
        fetchlog.bind()  # notes redirects and headers seen while the pages are read
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
            # PageSpeed and the page checks finish at their own times; join them here
            onpage.add_speed_issues(sections)
            await repo.update(audit_id, sections={"on_page": sections["on_page"]})
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
            await _report_usage(trace, meter, repo, audit_id)
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
            await _report_usage(trace, meter, repo, audit_id)
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
        await _report_usage(trace, meter, repo, audit_id)
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
    parts = urlsplit(url)
    url = f"{parts.scheme}://{parts.netloc}/"  # always audit from the site root
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


# ponytail: one radius for every clinic; make it per market if suburbs and cities need different reach.
CLINIC_RADIUS_KM = 8


async def _apify_places(
    http: httpx.AsyncClient,
    query: str,
    location: str,
    near: tuple[float, float] | None = None,
) -> list[dict[str, Any]]:
    """Google Maps results for `query`: around the clinic's coordinates when given (what a
    patient close to the clinic sees), else around the typed city. Apify ignores
    customGeolocation when a location text is sent, so only one of the two goes in."""
    body: dict[str, Any] = {
        "searchStringsArray": [query],
        "maxCrawledPlacesPerSearch": 20,
        "language": "en",
    }
    if near:
        body["customGeolocation"] = {
            "type": "Point",
            "coordinates": [near[1], near[0]],  # longitude first
            "radiusKm": CLINIC_RADIUS_KM,
        }
    else:
        body["locationQuery"] = location
    r = await http.post(
        f"https://api.apify.com/v2/acts/{settings.APIFY_GMAPS_ACTOR_ID}/run-sync-get-dataset-items",
        params={"token": settings.APIFY_API_TOKEN},
        json=body,
        timeout=90,
    )
    if r.status_code >= 400:
        raise AppError(
            502, "upstream_error", f"Competitor search failed ({r.status_code})"
        )
    items = r.json()
    return items if isinstance(items, list) else []


def _clinic_point(gbp: dict[str, Any]) -> tuple[float, float] | None:
    lat, lng = gbp.get("lat"), gbp.get("lng")
    if isinstance(lat, int | float) and isinstance(lng, int | float):
        return float(lat), float(lng)
    return None


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
    gbp = (audit.get("business") or {}).get("gbp") or {}
    # No typed place and the clinic's coordinates are known: search around the clinic.
    near = None if location else _clinic_point(gbp)
    if near:
        address = str(gbp.get("address") or "the clinic")
        location = f"within {CLINIC_RADIUS_KM} km of {address}"
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
            places = await _apify_places(http, query, location, near)
            items = []
            clinic_id = gbp.get("place_id")
            for rank, p in enumerate(places[:20], 1):
                site = p.get("website") or None
                host = _domain(urlsplit(site).hostname or "") if site else ""
                # The Google listing id is exact; the website is the backup when it is unknown.
                same_id = bool(clinic_id) and p.get("placeId") == clinic_id
                items.append(
                    {
                        "rank": rank,
                        "name": str(p.get("title") or ""),
                        "rating": p.get("totalScore"),
                        "review_count": p.get("reviewsCount"),
                        "website": site,
                        "is_this_business": same_id
                        or (bool(host) and host == audit["domain"]),
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


class AiVisibilityRequest(BaseModel):
    prompts: list[str] = Field(min_length=1, max_length=3)

    @field_validator("prompts")
    @classmethod
    def _clean(cls, value: list[str]) -> list[str]:
        out = list(dict.fromkeys(p.strip()[:200] for p in value if p.strip()))
        if not out:
            raise ValueError("at least one question is required")
        return out


async def _ai_job(
    repo: AuditRepository,
    http: httpx.AsyncClient,
    run_id: str,
    audit: dict[str, Any],
    prompts: list[str],
) -> None:
    async def save(data: dict[str, Any], cost: int, tokens: int) -> None:
        await repo.save_ai_run(run_id, data=data, cost_micro=cost, tokens=tokens)

    try:
        res = await ai_visibility.run(
            http, run_id=run_id, audit=audit, prompts=prompts, save=save
        )
        await repo.save_ai_run(
            run_id,
            status=res.status,
            data=res.data,
            error=res.error,
            cost_micro=res.cost_micro,
            tokens=res.tokens,
            finished=True,
        )
    except Exception:  # never leave a run stuck in `running`
        logger.exception("ai_visibility run %s crashed", run_id)
        await repo.save_ai_run(
            run_id,
            status="failed",
            error="AI visibility check failed unexpectedly",
            finished=True,
        )


async def _ai_guard(
    repo: AuditRepository, audit_id: str, profile: UserProfile, *, paid: bool = True
) -> dict[str, Any]:
    """Checks shared by the AI visibility endpoints. Returns the audit (wire shape).
    `paid=False` (writing the questions: one cheap call) skips the run rate limit and budget."""
    audit = to_wire(await _audit(repo, audit_id))
    if not ai_visibility.enabled():
        raise AppError(
            503,
            "upstream_error",
            "AI visibility is not set up yet (AI_VISIBILITY_MODELS, OPENROUTER_API_KEY).",
        )
    if audit["status"] in ("queued", "running"):
        raise AppError(409, "audit_running", "Wait for the audit to finish first.")
    if not paid:
        return audit
    rate_limit(f"ai_vis:{profile.id}", 6, 3600)
    budget = round(settings.AI_VISIBILITY_DAILY_BUDGET_USD * 1_000_000)
    if await repo.ai_spend_micro(profile.id) >= budget:
        raise AppError(
            429, "budget_reached", "Daily AI visibility budget reached. Try tomorrow."
        )
    return audit


@router.post("/research/audits/{audit_id}/ai-visibility")
async def start_ai_visibility(
    audit_id: str,
    body: AiVisibilityRequest,
    request: Request,
    profile: UserProfile = Depends(require_extension_access),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> Response:
    repo = _repo(request)
    audit = await _ai_guard(repo, audit_id, profile)
    run_id = await repo.create_ai_run(audit_id, profile.id)
    if run_id is None:
        raise AppError(
            409, "already_running", "An AI visibility check is already running."
        )
    task = asyncio.create_task(_ai_job(repo, http, run_id, audit, body.prompts))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return OrjsonResponse(to_wire(await _audit(repo, audit_id)), status_code=202)


class AiFullRequest(BaseModel):
    # Your own questions (the writer is skipped). Omit to let the app write them.
    prompts: list[str] | None = Field(default=None, max_length=100)
    n_prompts: int | None = Field(default=None, ge=1, le=100)
    runs: int | None = Field(default=None, ge=1, le=5)


def _spawn_full(
    repo: AuditRepository, http: httpx.AsyncClient, run_id: str, audit: dict[str, Any]
) -> None:
    task = asyncio.create_task(ai_report.run_job(repo, http, run_id, audit))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@router.post("/research/audits/{audit_id}/ai-visibility/questions")
async def ai_questions(
    audit_id: str,
    request: Request,
    profile: UserProfile = Depends(require_extension_access),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> dict[str, Any]:
    """Step 1 of the full report: write the questions and say how big the run would be.
    Nothing is saved and no run starts; the user reviews the questions, then approves them
    with POST .../full."""
    audit = await _ai_guard(_repo(request), audit_id, profile, paid=False)
    rate_limit(f"ai_q:{profile.id}", 20, 3600)
    cfg = ai_report.plan(None, None)
    prompts, source = await ai_report.make_prompts(http, audit, cfg["n_prompts"], {})
    return {
        "prompts": prompts,
        "source": source,
        "engines": [e["label"] for e in cfg["engines"]],
        "runs": cfg["runs"],
        "max_questions": settings.AI_VISIBILITY_FULL_PROMPTS,
        "max_calls": settings.AI_VISIBILITY_FULL_MAX_CALLS,
    }


@router.post("/research/audits/{audit_id}/ai-visibility/full")
async def start_ai_report(
    audit_id: str,
    body: AiFullRequest,
    request: Request,
    profile: UserProfile = Depends(require_extension_access),
    http: httpx.AsyncClient = Depends(get_http_client),
) -> Response:
    repo = _repo(request)
    audit = await _ai_guard(repo, audit_id, profile)
    mine = list(
        dict.fromkeys(
            " ".join(p.split())[:200] for p in body.prompts or [] if p.strip()
        )
    )
    if len(mine) > settings.AI_VISIBILITY_FULL_PROMPTS:
        raise AppError(
            422,
            "too_many_questions",
            f"At most {settings.AI_VISIBILITY_FULL_PROMPTS} questions. Remove "
            f"{len(mine) - settings.AI_VISIBILITY_FULL_PROMPTS}.",
        )
    # The user approves these exactly, so nothing is dropped silently. A question that names
    # the clinic would inflate the score, so it is refused instead.
    names = ai_visibility.build_target(audit).patterns
    if bad := next((p for p in mine if any(pat.search(p) for pat in names)), None):
        raise AppError(
            422,
            "question_names_clinic",
            f"Remove the clinic's name from this question, or the score is inflated: {bad}",
        )
    cfg = ai_report.plan(len(mine) or body.n_prompts, body.runs)
    if mine:
        cfg["prompts"] = mine
        cfg["prompts_source"] = "user"
        cfg["n_prompts"] = len(cfg["prompts"])
        cfg["calls"] = cfg["n_prompts"] * len(cfg["engines"]) * cfg["runs"]
    if cfg["calls"] > settings.AI_VISIBILITY_FULL_MAX_CALLS:
        raise AppError(
            422,
            "too_many_calls",
            f"This run would make {cfg['calls']} calls; the limit is "
            f"{settings.AI_VISIBILITY_FULL_MAX_CALLS}. Use fewer questions or repeats.",
        )
    run_id = await repo.create_ai_run(audit_id, profile.id, kind="full", config=cfg)
    if run_id is None:
        raise AppError(
            409, "already_running", "An AI visibility check is already running."
        )
    _spawn_full(repo, http, run_id, audit)
    return OrjsonResponse(to_wire(await _audit(repo, audit_id)), status_code=202)


async def resume_full_runs(repo: AuditRepository, http: httpx.AsyncClient) -> int:
    """At start-up: continue full reports that a restart interrupted (answers already paid for
    are kept). Lite runs are not resumed; the sweeper fails them."""
    n = 0
    for run_id in await repo.running_full_runs():
        run = await repo.get_ai_run(run_id)
        if run is None:
            continue
        audit = await repo.get(run["audit_id"])
        if audit is None:
            continue
        _spawn_full(repo, http, run_id, to_wire(audit))
        n += 1
    return n


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
    """Full answer texts of one report, a page at a time (they are too big for the audit)."""
    repo = _repo(request)
    try:
        run = await repo.get_ai_run(run_id)
    except ValueError:  # not a UUID
        run = None
    if run is None or run["kind"] != "full":
        raise AppError(404, "run_not_found", "AI visibility report not found")
    rows = await repo.ai_answer_page(
        run_id, engine=engine, prompt_idx=prompt, limit=limit, offset=offset
    )
    return {
        "prompts": run["config"].get("prompts", []),
        "items": [
            {
                "prompt": r["prompt_idx"],
                "engine": r["engine"],
                "run": r["run_no"],
                "ok": r["status"] == "ok",
                "text": ai_visibility.stored_text(r["text"] or ""),
                "sources": r["urls"][:20],
                "error": r["error"],
                "facts": r["facts"],
            }
            for r in rows
        ],
    }


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
