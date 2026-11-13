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
    page_signals,
    page_types,
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
    "types": "Check page types",
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
    """Writes the step-by-step run log shown in the panel. A write problem never touches the audit.

    The panel folds the log by step id, the last event of a step winning. So a dropped "done"
    leaves the step "running" for ever. The newest event of each step that could not be written
    is kept, and flush() writes it again before the audit is marked finished."""

    def __init__(self, repo: AuditRepository, audit_id: str) -> None:
        self._repo, self._id = repo, audit_id
        self._started: dict[str, float] = {}
        self._open: set[str] = set()
        self._unwritten: dict[str, dict[str, Any]] = {}

    async def _write(self, event: dict[str, Any], wait: float) -> bool:
        try:
            async with asyncio.timeout(wait):
                await self._repo.add_trace(self._id, event)
            return True
        except Exception:
            logger.warning("audit %s: trace write failed", self._id, exc_info=True)
            return False

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
        if await self._write(event, TRACE_WRITE_S):
            self._unwritten.pop(step, None)  # a later event of the step supersedes
        else:
            self._unwritten[step] = event

    async def skip(self, reason: str, *steps: str) -> None:
        for step in steps:
            await self.report(step, "skipped", reason=reason)

    async def fail_open(self, error: str) -> None:
        for step in list(self._open):
            await self.report(step, "failed", error=error)

    async def flush(self) -> None:
        """Write again the newest event of every step whose write failed, with more time. A step
        still open at this point never reported its end: it is closed as failed, not left
        "running" on a finished audit."""
        await self.fail_open("The step did not finish")
        for step, event in list(self._unwritten.items()):
            if await self._write(event, TRACE_FLUSH_S):
                self._unwritten.pop(step, None)


TRACE_WRITE_S = 2.0  # one log write while the audit runs: it must never slow the audit
TRACE_FLUSH_S = 10.0  # the second try at the end, when nothing else is waiting


async def _home(
    http: httpx.AsyncClient, url: str, hints: dict[str, str], trace: _Trace
) -> tuple[dict[str, Any], str, str, str, bool]:
    """Returns (sections, final URL, home HTML, via, rendered).

    Firecrawl and the direct fetch start together. The page we audit is Firecrawl's browser view
    when it has one (scripts have run, so JSON-LD, chat widgets and booking buttons that
    JavaScript adds are there); otherwise the direct read. The direct fetch is free and always
    says whether the site answers us: via is "firecrawl" when it does not, so the crawl reads
    every other page through Firecrawl and no direct link checks are made. It also records the
    home page's redirects and headers (fetchlog)."""
    await trace.report("home", "running")
    (
        (direct, final_direct, direct_error),
        (browser, final_browser, browser_why),
    ) = await asyncio.gather(_direct_home(url), _browser_home(http, url))
    if direct_error is not None and direct_error.code == "url_not_allowed":
        raise direct_error  # an address we refuse is refused, whoever could read it
    via = "direct" if direct is not None else "firecrawl"
    if browser is not None:
        html, final_url, rendered = browser, final_browser, True
        reason = direct_error.message if direct_error else None  # why direct failed
    elif direct is not None:
        html, final_url, rendered = direct, final_direct, False
        reason = browser_why  # why Firecrawl had nothing (None: no key)
    else:
        assert direct_error is not None
        raise direct_error
    await trace.report(
        "home",
        "done",
        via="firecrawl" if rendered else "direct",
        reason=reason,
        url=final_url,
        size=len(html),
    )
    await trace.report("analyze", "running")
    sections = site_audit.analyze(html, final_url, hints)
    if (
        rendered
    ):  # a widget a script builds is in this HTML: no second rendered fetch needed
        sections["convert"]["chat_widget"] = site_crawl.detect_chat_rendered(html)
    await trace.report("analyze", "done")
    return sections, final_url, html, via, rendered


async def _direct_home(url: str) -> tuple[str | None, str, AppError | None]:
    """(HTML, final URL, error): our own fetch, SSRF-guarded. A bot wall counts as an error."""
    try:
        html, final_url = await site_audit.fetch_html(url)
    except AppError as exc:
        return None, url, exc
    if site_crawl._blocked(html):
        # HTTP 200 with a bot-protection page: never audit the wall as the clinic's site.
        return (
            None,
            final_url,
            AppError(
                422,
                "site_blocked",
                "The website's bot protection blocked our reader. Try again later.",
            ),
        )
    return html, final_url, None


async def _browser_home(
    http: httpx.AsyncClient, url: str
) -> tuple[str | None, str, str | None]:
    """(HTML, final URL, why it is missing): the page as a browser shows it, through Firecrawl.
    No key: (None, url, None)."""
    if not settings.FIRECRAWL_API_KEY:
        return None, url, None
    why: dict[str, str] = {}
    meta: dict[str, Any] = {}
    try:
        html = await site_crawl.scrape_home(http, url, why, meta)
    except (httpx.HTTPError, ValueError) as exc:
        return None, url, f"Firecrawl request failed ({_why(exc)})"
    status = meta.get("statusCode")
    if html and site_crawl._blocked(html):
        return None, url, "Firecrawl got a bot-protection page"
    if html and isinstance(status, int) and status >= 400:
        return None, url, f"The site answered HTTP {status}"
    if not html:
        return None, url, why.get("error") or "Firecrawl returned no page"
    return html, _final_url(meta, url), None


def _final_url(meta: dict[str, Any], requested: str) -> str:
    """Where Firecrawl ended up, checked like any URL we fetch; the requested URL if unusable."""
    for key in ("url", "sourceURL"):
        value = meta.get(key)
        if isinstance(value, str) and value:
            try:
                return site_audit.normalize_url(value)[0]
            except AppError:
                break
    return requested


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


def _phone_from_pages(sections: dict[str, Any], crawled: dict[str, str]) -> None:
    """The clinic's phone when the home page has none (Viva shows it only on /contact): the
    contact page's tel: link first, else the number most pages link to. Without it the phone
    cannot be compared with the Google profile's."""
    nap = sections["business"]["nap"]
    if nap.get("phone"):
        return
    found = [
        (u, phone)
        for u, html in crawled.items()
        if (phone := site_audit.raw_phone(html))
    ]
    if not found:
        return
    contact = next((p for u, p in found if "contact" in urlsplit(u).path.lower()), None)
    counts: dict[str, int] = {}
    for _, phone in found:
        counts[phone] = counts.get(phone, 0) + 1
    nap["phone"] = contact or max(counts, key=lambda k: counts[k])


def site_facts(
    sections: dict[str, Any],
    home_html: str,
    urls: list[str],
    crawled: dict[str, str],
    posts: list[dict[str, Any]] | None,
    menu: site_crawl.Menu,
) -> dict[str, Any]:
    """The Site tab from the crawl: URL and menu rules, then what the site's own structured
    data says (services and their pages). Returns the structured data lists; their areas are
    graded with the AI step. The golden tests call this too, so they score what audits run."""
    site_crawl.enrich(sections, urls, crawled, posts, menu)
    _phone_from_pages(sections, crawled)
    schema = site_audit.schema_lists([home_html, *crawled.values()])
    # The towns of the clinic's own addresses are areas too (its office locations): a page
    # about one (/plano-tx) is then found as that location's page.
    if not schema["localities"] and (town := page_signals.title_town(crawled)):
        schema["localities"] = [
            town
        ]  # "| Plano, TX |" on most titles: the clinic's town
    schema["areas"] = list(dict.fromkeys([*schema["areas"], *schema["localities"]]))
    sections["site"]["schema_lists"] = schema
    site_crawl.apply_schema_services(
        sections, schema["services"], urls, menu, schema["areas"]
    )
    return schema


async def _confirm_leftover_text(
    http: httpx.AsyncClient, sections: dict[str, Any]
) -> None:
    """Leftover builder text is reported only if a visitor sees it. The raw HTML can hold a
    template a script replaces on load (Viva's specials slider: one "Title Goes Here" slide in
    the HTML, five real cards in the browser), so each page flagged for it is read again as a
    browser shows it, and dropped when the text is gone. Without a key it is kept unchecked."""
    site = sections["site"]
    flagged = [p for p in site.get("unfinished_pages") or [] if p.get("counted")]
    if not flagged or not settings.FIRECRAWL_API_KEY:
        return
    gone: set[str] = set()
    for p in flagged[:LEFTOVER_CHECKS]:
        try:
            html = await site_crawl.scrape_rendered(http, p["url"])
        except httpx.HTTPError:
            continue  # not checked: kept
        if html and page_signals.placeholder_text(html) is None:
            gone.add(p["url"])
    site["unfinished_pages"] = [
        p for p in site["unfinished_pages"] if p["url"] not in gone
    ]
    site["placeholder_pages"] = [u for u in site["placeholder_pages"] if u not in gone]


# Pages re-read in the browser view to confirm leftover text (one Firecrawl call each).
LEFTOVER_CHECKS = 5


async def _page_types(
    http: httpx.AsyncClient,
    sections: dict[str, Any],
    urls: list[str],
    crawled: dict[str, str],
    menu: site_crawl.Menu,
    trace: _Trace,
) -> None:
    """The AI reads the pages the rules cannot settle (page_types). Without a key, or when the
    call fails, the rules' answer stands and the Site tab says so ("types_by": "rules")."""
    services = sections["site"]["services"]
    services["types_by"] = "rules"
    if not settings.OPENROUTER_API_KEY:
        await trace.skip("OpenRouter key not set", "types")
        return
    todo = page_types.candidates(sections, urls, crawled, menu)
    await trace.report("types", "running")
    try:
        labels = await page_types.read_types(http, todo, crawled)
    except (AppError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("page types failed", exc_info=True)
        await trace.report("types", "failed", error=_why(exc))
        return
    page_types.apply(sections, labels, crawled)
    services["types_by"] = "rules+ai"
    await trace.report(
        "types",
        "done",
        pages=len(labels),
        services=sum(1 for v in labels.values() if v["label"] == "service"),
    )


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
    rendered: bool = False,
) -> bool:
    """Add whole-site, AI and GBP data. Returns False if a provider step failed."""
    ok = True
    pages = {final_url: home_html}
    urls: list[str] = []
    schema: dict[str, Any] = {"services": [], "areas": []}
    menu = site_crawl.nav_links(home_html, final_url)
    try:
        urls, crawled, crawl_ok, sitemap = await site_crawl.crawl(
            http, final_url, home_html, via, trace.report, menu
        )
        ok = crawl_ok  # False when the site map failed; the menu-based crawl still ran
        await trace.report("enrich", "running")
        posts = await site_crawl.blog_posts(http, urls, crawled, final_url, sitemap)
        schema = site_facts(sections, home_html, urls, crawled, posts, menu)
        await _page_types(http, sections, urls, crawled, menu, trace)
        await _confirm_leftover_text(http, sections)
        if not rendered:
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
                sections,
                await site_ai.analyze(http, pages, names),
                pages,
                urls,
                extra_areas=schema["areas"],
            )
            await trace.report("ai", "done", pages=len(pages))
        except (AppError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("audit %s: AI page analysis failed", audit_id, exc_info=True)
            await trace.report("ai", "failed", error=_why(exc))
            ok = False  # keyword results are kept
    else:
        await trace.skip("OpenRouter key not set", "ai")
        if schema[
            "areas"
        ]:  # the site names its areas itself: grade them without the AI
            site_ai.apply_areas(sections, schema["areas"], pages, urls)
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
            sections["business"]["gbp_status"] = "found" if gbp else "not_found"
            sections["business"]["gbp_note"] = (
                None if gbp else f"Searched Google Maps for: {', '.join(tried)}."
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
            sections["business"]["gbp_status"] = "not_checked"
            sections["business"]["gbp_note"] = f"The search failed ({_why(exc)})."
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


async def _steps(
    repo: AuditRepository,
    http: httpx.AsyncClient,
    audit_id: str,
    url: str,
    hints: dict[str, str],
    trace: _Trace,
) -> bool:
    """Every step of one audit, in order. Returns True when all of them worked, False when a
    provider step failed (the audit is then `partial`). Raises when the audit cannot go on."""
    speed: asyncio.Task[bool] | None = None
    try:
        sections, final_url, home_html, via, rendered = await _home(
            http, url, hints, trace
        )
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
            repo,
            http,
            audit_id,
            sections,
            final_url,
            home_html,
            via,
            hints,
            trace,
            rendered,
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
        return ok
    finally:
        if speed and not speed.done():
            speed.cancel()


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
        try:
            # A step that never answers must not hold the audit (and one of the few audit
            # slots, and the "one audit per site" rule) for ever: the audit ends by this time.
            async with asyncio.timeout(settings.AUDIT_MAX_S) as deadline:
                ok = await _steps(repo, http, audit_id, url, hints, trace)
        except Exception as exc:  # never leave an audit stuck in `running`
            if isinstance(exc, AppError):
                message = shown = exc.message
            elif deadline.expired():
                logger.error("audit %s ran past %ss", audit_id, settings.AUDIT_MAX_S)
                message = shown = (
                    "The audit took too long and was stopped. Run it again."
                )
            else:
                logger.exception("audit %s crashed", audit_id)
                message, shown = "Unexpected error", "Audit failed unexpectedly"
            await trace.fail_open(message)
            await _report_usage(trace, meter, repo, audit_id)
            await trace.report("final", "failed", outcome="failed", error=message)
            await trace.flush()
            await repo.update(
                audit_id,
                status="failed",
                error=shown,
                finished=True,
                state={k: "failed" for k in INITIAL_STATE},
            )
            return
        await _report_usage(trace, meter, repo, audit_id)
        await trace.report("final", "done", outcome="ready" if ok else "partial")
        await trace.flush()
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
