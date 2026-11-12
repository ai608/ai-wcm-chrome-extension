"""The audit pipeline: start an audit, run its steps in the background, keep its state.
No HTTP here; the routes in app/api/v1/research.py call this."""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import asyncpg
import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.repositories.audit_repository import AuditRepository
from app.services import (
    apollo,
    crawl_access,
    fetchlog,
    onpage,
    probes,
    site_ai,
    site_audit,
    site_crawl,
    site_score,
    usage,
)

logger = logging.getLogger(__name__)

# Everything site_audit.analyze fills from the home page; the rest needs provider keys.
INITIAL_STATE = {k: "pending" for k in site_audit.SECTION_KEYS}
# ponytail: in-process jobs, max 3 at once, single instance. Move to a queue if scaled out.
_sem = asyncio.Semaphore(3)
_tasks: set[asyncio.Task[None]] = set()
_start_lock = (
    asyncio.Lock()
)  # ponytail: one lock for all domains; per-domain if starts queue up
# After the other steps finish, wait at most this long for PageSpeed before scoring.
PAGESPEED_WAIT_S = 60.0


def track(task: "asyncio.Task[None]") -> None:
    """Keep a reference to a background job until it ends (the loop holds only weak ones)."""
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _digits(value: object) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())[-10:]


def domain_of(host: str) -> str:
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


async def _rendered_chat(
    http: httpx.AsyncClient, sections: dict[str, Any], url: str
) -> None:
    """The HTML we crawl is what the server sent, so a widget a script builds later (a tag
    manager, a loader) is missing from it. When nothing was found, look at the rendered page."""
    convert = sections["convert"]
    if convert.get("chat_widget") or not settings.FIRECRAWL_API_KEY:
        return
    try:
        html = await site_crawl.scrape_rendered(http, url)
    except httpx.HTTPError:
        logger.warning("rendered chat check failed for %s", url, exc_info=True)
        return
    if html:
        convert["chat_widget"] = site_crawl.detect_chat_rendered(html)


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
        await _rendered_chat(http, sections, final_url)
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
            site_ai.apply(
                sections, await site_ai.analyze(http, pages, names), pages, urls
            )
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
        domain = domain_of(urlsplit(final_url).hostname or "")
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
    if settings.APOLLO_API_KEY:
        await trace.report("company", "running")
        try:
            domain = domain_of(urlsplit(final_url).hostname or "")
            found = await apollo.company(http, domain)
            sections["business"]["company"] = found
            await repo.update(
                audit_id,
                sections={"business": sections["business"]},
                state={"business": "ready"},
            )
            await trace.report("company", "done", matched=bool(found))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("audit %s: Apollo lookup failed", audit_id, exc_info=True)
            await trace.report("company", "failed", error=_why(exc))
            ok = False
    else:
        await trace.skip("Apollo key not set", "company")
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
                domain=domain_of(urlsplit(final_url).hostname or ""),
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


async def start(
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
    domain = domain_of(host)  # www.example.com and example.com are one site
    async with _start_lock:  # the check and the insert must not interleave
        newest = await repo.latest(domain)
        if newest and newest["status"] in ("queued", "running"):
            return newest, False  # force never starts a second run of the same site
        if not force and (fresh := await repo.latest(domain, fresh_only=True)):
            return fresh, False
        row = await repo.create(user_id, url, domain, INITIAL_STATE)
    track(asyncio.create_task(_run(repo, http, str(row["id"]), url, hints)))
    return row, True


async def fetch_audit(repo: AuditRepository, audit_id: str) -> asyncpg.Record:
    row = await repo.get(audit_id)
    if row is None:
        raise AppError(404, "audit_not_found", "Audit not found")
    return row
