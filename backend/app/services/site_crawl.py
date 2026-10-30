"""Whole-site data for an audit: Firecrawl (map + scrape) and Apify (Google Business Profile).

site_audit.analyze() only sees the home page. This module adds the rest of the site to the
`site` and `convert` sections and fills `business.gbp`. Every provider call is optional:
without a key, or on any provider error, the home-page result is kept as it is.
"""

import asyncio
import html as html_lib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from itertools import zip_longest
from typing import Any, NamedTuple
from urllib.parse import urljoin, urlsplit

import httpx
from selectolax.lexbor import LexborHTMLParser

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.constants import (
    BOOKING,
    CHAT,
    KIND_TRUST,
    PLACEHOLDER_TEXT,
    SERVICES,
    TRUST,
    TRUST_LINK_TEXT,
)
from app.services.site_audit import TRANSIENT_STATUS, fetch_html, raw_phone

logger = logging.getLogger(__name__)

FIRECRAWL = "https://api.firecrawl.dev/v2"
PAGESPEED = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
MAX_URLS = 500
# Slots per tier (see plan()); slots a tier does not use pass to the next one. D gets the rest.
TIER_CAPS = {"A": 20, "B": 12, "C": 6}
MIN_TEXT_CHARS = 500  # less visible text than this: the page likely needs JavaScript

CITY = re.compile(
    r"/(locations?|service-areas?|areas-we-serve|near-me)(/|$)|-near-me", re.IGNORECASE
)
BLOG = re.compile(r"/(blog|blogs|news|articles|resources)/", re.IGNORECASE)
BLOG_INDEX = re.compile(r"/(blog|blogs|news|articles|resources)/?$", re.IGNORECASE)
# Archive and listing links on a blog page that are not posts.
NOT_POST = re.compile(
    r"/(category|tag|author|page|feed|wp-content|wp-json)/", re.IGNORECASE
)
# WordPress post sitemaps (Yoast / Rank Math first, then WordPress core).
POST_SITEMAPS = ("/post-sitemap.xml", "/wp-sitemap-posts-post-1.xml")
# Then the general sitemaps, where only URLs under a blog-like path count as posts.
GENERAL_SITEMAPS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")
SITEMAP_FETCHES = 6
MAX_POSTS = 1000
PROOF = {
    "before_after": re.compile(
        r"before-?and-?after|before-after|gallery|results", re.IGNORECASE
    ),
    "testimonial": re.compile(r"testimonial", re.IGNORECASE),
    "reviews": re.compile(r"/reviews?(/|$)", re.IGNORECASE),
    "case_study": re.compile(r"case-stud", re.IGNORECASE),
}


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _slug(url: str) -> str:
    return urlsplit(url).path.lower().replace("-", " ").replace("_", " ")


def _service_of(url: str) -> str | None:
    slug = _slug(url)
    return next(
        (name for name, terms in SERVICES.items() if any(t in slug for t in terms)),
        None,
    )


async def map_site(http: httpx.AsyncClient, url: str) -> list[str]:
    r = await http.post(
        f"{FIRECRAWL}/map",
        headers={"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"},
        json={"url": url, "limit": MAX_URLS},
        timeout=60,
    )
    r.raise_for_status()
    links = r.json().get("links") or []
    home = _host(url)
    urls = [str(x.get("url") if isinstance(x, dict) else x) for x in links]
    return list(
        dict.fromkeys(u for u in urls if u.startswith("http") and _host(u) == home)
    )


async def scrape(http: httpx.AsyncClient, url: str) -> str | None:
    """Page HTML through Firecrawl; None when it has none. One retry after a timeout, a
    connection error, 429 or 5xx; a 402 (out of credits) or 4xx is final."""
    for attempt in (1, 2):
        try:
            r = await http.post(
                f"{FIRECRAWL}/scrape",
                headers={"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"},
                json={"url": url, "formats": ["rawHtml"], "onlyMainContent": False},
                timeout=60,
            )
        except httpx.HTTPError:
            if attempt == 2:
                raise
        else:
            wait = r.headers.get("retry-after", "")
            if r.status_code not in TRANSIENT_STATUS or attempt == 2:
                break
            if r.status_code == 429 and wait.isdigit() and int(wait) > 5:
                break
        await asyncio.sleep(settings.CRAWL_RETRY_DELAY_S)
    if r.status_code >= 400:
        return None
    data = r.json().get("data") or {}
    html = data.get("rawHtml") or data.get("html")
    return html if isinstance(html, str) and html.strip() else None


# Called as report(step_id, status, **detail); used to show the crawl live in the panel.
Report = Callable[..., Awaitable[None]]

# Pages that list a clinic's services; their children (/treatments/<slug>) are service pages.
HUB = re.compile(
    r"^/(services|treatments|procedures|menu|our-services|med-spa-services|injectables"
    r"|aesthetics|wellness)(\.html?)?$",
    re.IGNORECASE,
)
# Files and system paths: never a page worth reading.
JUNK = re.compile(
    r"\.(pdf|jpe?g|png|webp|gif|svg|mp4|zip|xml|ics|kml)$"
    r"|/(wp-json|wp-admin|wp-content|feed|cart|checkout|my-account|login|cdn-cgi)(/|$)",
    re.IGNORECASE,
)
# Menu dropdowns that hold no services, by their label.
NOT_SERVICE_MENU = re.compile(
    r"about|news|blog|contact|resource|patient|career|shop|store", re.IGNORECASE
)
TIER_NAMES = {
    "A": "Services",
    "B": "Other treatments",
    "C": "About the clinic",
    "D": "More service pages",
    "E": "Other pages",
}
CONTEXT = ("team_page", "pricing_page", "financing_page", "about_page", "faq_page")
# Firecrawl map runs next to the menu reads; on a big blog it took 46 s. It only adds
# extra pages, so a slow map is dropped instead of holding up the audit.


MIN_MENU_LINKS = 8
MENU_NODE = re.compile(r"menu|nav", re.IGNORECASE)


class Menu(NamedTuple):
    """The site menu read from the home page."""

    children: dict[str, str]  # page in a dropdown -> the dropdown's label
    parents: dict[str, str]  # dropdown's own page -> its label
    top: dict[str, str]  # every page linked from the menu -> its link text, lower case
    labels: dict[str, dict[str, Any]]  # page -> what the model made of its link

    def has(self, url: str) -> bool:
        return url in self.top


NO_MENU = Menu({}, {}, {}, {})


def clean_url(url: str, home: str) -> str | None:
    """`url` on the home page's scheme and host, with no query or fragment, so www/http
    variants become one URL. None for another host, a file or a system path."""
    parts, base = urlsplit(url), urlsplit(home)
    if parts.scheme not in ("http", "https") or _host(url) != _host(home):
        return None
    path = parts.path or "/"
    # ponytail: the query is dropped, so WordPress ?page_id= links collapse to one; keep
    # page_id if a site without pretty links shows up.
    return None if JUNK.search(path) else f"{base.scheme}://{base.netloc}{path}"


def _dropdown_of(link: Any) -> tuple[str, str | None] | None:
    """(label, href) of the menu item whose dropdown holds `link`; None for a top-level item."""
    own = None
    node = link.parent
    while node is not None:
        if node.tag == "li":
            if own is None:
                own = node
            else:
                head = next(
                    (c for c in node.css("a, span, button") if c.text(strip=True)), None
                )
                if head is None:
                    return None
                href = head.attributes.get("href") if head.tag == "a" else None
                return " ".join(head.text(strip=True).split()), href
        node = node.parent
    return None


def nav_links(html: str, home: str) -> Menu:
    """The site menu. The clinic's own menu is the best list of its services, whatever its
    URLs are called: every page in a dropdown is a candidate, unless the dropdown is About,
    News and the like."""
    menu = Menu({}, {}, {}, {})
    doc = LexborHTMLParser(html)
    for tag in doc.css("script, style, noscript"):
        tag.decompose()
    roots = doc.css("nav, header, [role=navigation]")
    if sum(len(r.css("a[href]")) for r in roots) < MIN_MENU_LINKS:
        roots += [
            n
            for n in doc.css("ul, div, section, aside")
            if MENU_NODE.search(
                f"{n.attributes.get('class') or ''} {n.attributes.get('id') or ''}"
            )
        ]
    for root in roots:
        for a in root.css("a[href]"):
            url = clean_url(urljoin(home, a.attributes.get("href") or ""), home)
            if url is None:
                continue
            text = " ".join(a.text(strip=True).split()).lower()
            if not menu.top.get(url):
                menu.top[url] = text
            dropdown = _dropdown_of(a)
            if dropdown is None:
                continue
            label, href = dropdown
            menu.children.setdefault(url, label)
            # a dropdown heading linked to "#" is no page
            if href and not href.startswith("#"):
                parent = clean_url(urljoin(home, href), home)
                menu.parents.setdefault(parent or "", label)
    menu.parents.pop("", None)
    return menu


def _trust_key(url: str, menu: Menu = NO_MENU) -> str | None:
    """Which trust page this is: by its URL, else by the text of its menu link."""
    if url in menu.labels:
        return KIND_TRUST.get(menu.labels[url]["kind"])
    low = url.lower()
    by_url = next((k for k, _, words in TRUST if any(w in low for w in words)), None)
    if by_url:
        return by_url
    text = menu.top.get(url, "")
    return next(
        (k for k, words in TRUST_LINK_TEXT.items() if any(w in text for w in words)),
        None,
    )


def _under_hub(url: str) -> bool:
    path = urlsplit(url).path.strip("/").lower()
    return "/" in path and bool(HUB.match("/" + path.split("/")[0]))


def classify(url: str, menu: Menu = NO_MENU) -> str:
    """One class per URL; the first rule that matches wins."""
    path = urlsplit(url).path.rstrip("/").lower()
    deep = path.strip("/").count("/") >= 1
    if BLOG.search(url) and deep:
        return "blog_post"
    if BLOG_INDEX.search(url):
        return "blog_index"
    if label := menu.labels.get(url):
        kind = label["kind"]
        if kind == "service":
            return "service" if _service_of(url) else "menu_child"
        return {"services_hub": "hub"}.get(kind) or (
            "trust" if kind in KIND_TRUST else "other"
        )
    if HUB.match(path) or (
        url in menu.parents and not NOT_SERVICE_MENU.search(menu.parents[url])
    ):
        return "hub"
    if _service_of(url):
        return "service"
    if _under_hub(url):
        return "hub_child"
    trust, city, proof = (
        _trust_key(url, menu),
        CITY.search(url),
        any(p.search(url) for p in PROOF.values()),
    )
    if (
        url in menu.children
        and not NOT_SERVICE_MENU.search(menu.children[url])
        and not (trust or city or proof)
    ):
        return "menu_child"
    if trust:
        return "trust"
    if city:
        return "city"
    return "proof" if proof else "other"


def tiers(
    urls: list[str],
    home: str,
    menu: Menu = NO_MENU,
    posts: set[str] | None = None,
) -> dict[str, list[str]]:
    """Candidate pages by tier, best first, before any cut.

    A: service hubs, then the main page of each known service. Only a page in the menu or
       under a hub can be a main page: a URL that just contains a service word is often a
       blog post ("/what-to-expect-with-first-botox-appointment").
    B: every other page of the menu, in menu order (unknown treatments, and a second page of a
       known service), then unknown pages under a hub.
    C: pages the AI reads for providers, pricing and areas, then the blog index.
    D: the other pages of each known service that are not in the menu, one round per service.
    E: the rest; read only when the whole site fits in MAX_PAGES.
    `posts` are URL keys from the post sitemap: blog posts, never service pages.
    """
    posts = posts or set()
    hubs: list[str] = []
    services: dict[str, list[str]] = {}
    in_menu: list[str] = []
    under_hub: list[str] = []
    context: dict[str, str] = {}
    cities: list[str] = []
    rest: list[str] = []
    blog_index = None
    for u in urls:
        if _key(u) in posts or _key(u) == _key(home) or NOT_POST.search(u):
            continue  # posts, home, and archives such as /tag/botox are no service
        cls = classify(u, menu)
        if cls == "hub":
            hubs.append(u)
        elif cls == "service":
            services.setdefault(_service_of(u) or "", []).append(u)
        elif cls == "menu_child":
            in_menu.append(u)
        elif cls == "hub_child":
            under_hub.append(u)
        elif (
            cls == "trust"
            and (k := _trust_key(u, menu)) in CONTEXT
            and k not in context
        ):
            context[k] = u
        elif cls == "blog_index":
            blog_index = blog_index or u
        elif cls == "city":
            cities.append(u)
        elif cls != "blog_post":
            rest.append(u)
    mains: list[str] = []
    others: list[list[str]] = []
    for name in SERVICES:
        if name not in services:
            continue
        pages = sorted(
            services[name],
            key=lambda u: (urlsplit(u).path.strip("/").count("/"), len(u), u),
        )
        main = next((u for u in pages if menu.has(u) or _under_hub(u)), None)
        if main:
            mains.append(main)
        # a page the clinic put in its menu is never "more pages": it goes to B
        in_menu += [u for u in pages if u != main and menu.has(u)]
        others.append([u for u in pages if u != main and not menu.has(u)])
    order = {
        u: i for i, u in enumerate(urls)
    }  # urls start with the menu, in menu order
    in_menu.sort(key=lambda u: order[u])
    city_hub = next(
        (
            u
            for u in cities
            if re.search(r"/(locations?|service-areas?)/?$", u, re.IGNORECASE)
        ),
        None,
    )
    extra = [u for pages in zip_longest(*others) for u in pages]
    return {
        "A": hubs + mains,
        "B": in_menu + sorted(under_hub, key=len),
        "C": [context[k] for k in CONTEXT if k in context]
        + [u for u in (city_hub, blog_index) if u],
        "D": [u for u in extra if u],
        "E": [u for u in cities if u != city_hub] + rest,
    }


def plan(
    urls: list[str],
    home: str,
    menu: Menu = NO_MENU,
    posts: set[str] | None = None,
    taken: list[str] | None = None,
) -> tuple[list[str], list[dict[str, Any]], str]:
    by_tier = tiers(urls, home, menu, posts)
    taken = taken or []
    total = sum(len(b) for b in by_tier.values())
    mode = "all" if total <= settings.CRAWL_MAX_PAGES else "tiers"
    picked: dict[str, list[str]] = {}
    spare, left = 0, settings.CRAWL_MAX_PAGES
    for name, pages in by_tier.items():
        old = [u for u in pages if u in taken]
        new = [u for u in pages if u not in taken]
        if taken and name not in ("D", "E"):
            new = []
        if mode == "all":
            room = len(pages)
        elif name in TIER_CAPS:
            room = TIER_CAPS[name] + spare
        else:
            room = left if name == "D" else 0
        picked[name] = old + new[: max(min(room, left) - len(old), 0)]
        left -= len(picked[name])
        spare = max(room - len(picked[name]), 0) if name in TIER_CAPS else 0
    groups = [
        {
            "name": TIER_NAMES[name],
            "found": len(pages),
            "picked": picked[name],
            "skipped": len(pages) - len(picked[name]),
        }
        for name, pages in by_tier.items()
    ]
    return [u for name in by_tier for u in picked[name]], groups, mode


def _visible_chars(html: str) -> int:
    doc = LexborHTMLParser(html)
    for tag in doc.css("script, style, noscript, svg"):
        tag.decompose()
    body = doc.css_first("body")
    return len(" ".join(body.text(separator=" ", strip=True).split())) if body else 0


class _Reader:
    """Reads one page: directly first (free, SSRF-guarded by fetch_html), then with Firecrawl
    when the direct fetch fails or returns almost no text (blocked, or built by JavaScript).
    At most settings.FIRECRAWL_FALLBACKS pages fall back. When the home page itself needed Firecrawl,
    the site blocks us, so every page goes to Firecrawl."""

    def __init__(self, http: httpx.AsyncClient, home: str, direct: bool) -> None:
        self.http, self.home, self.direct = http, home, direct
        self.fallbacks = (
            settings.FIRECRAWL_FALLBACKS if settings.FIRECRAWL_API_KEY else 0
        )

    async def __call__(self, url: str) -> tuple[str | None, str]:
        thin = None
        if self.direct:
            try:
                html, final = await fetch_html(url)
            except AppError:
                html, final = None, url
            if html is not None and _host(final) != _host(self.home):
                return None, "direct"  # redirected off the site
            if html is not None and _visible_chars(html) >= MIN_TEXT_CHARS:
                return html, "direct"
            thin = html
            if self.fallbacks <= 0:
                return thin, "direct"
            self.fallbacks -= 1
        elif not settings.FIRECRAWL_API_KEY:
            return None, "direct"
        try:
            return await scrape(self.http, url) or thin, "firecrawl"
        except (httpx.HTTPError, ValueError):
            return thin, "firecrawl"


def _why(exc: Exception) -> str:
    """Never str(exc): httpx errors can carry the request URL."""
    if isinstance(exc, httpx.TimeoutException):
        return "Timed out"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


async def crawl(
    http: httpx.AsyncClient,
    url: str,
    home_html: str = "",
    via: str = "direct",
    report: Report | None = None,
    menu: Menu | None = None,
) -> tuple[list[str], dict[str, str], bool, list[dict[str, Any]]]:
    """Find, choose and read the site's pages.

    1. Start Firecrawl map (when a key is set) in the background.
    2. Read the post sitemap, so blog posts are never taken for service pages.
    3. Plan from the home page menu and links, and start reading those pages at once.
    4. When map returns, add its new pages to "More service pages" and "Other pages" only.

    Returns (every URL found, HTML by URL in reading order, ok, sitemap posts). ok is False
    when the map failed with an error; a map that is only slow is dropped and ok stays True.
    Reads stop settings.CRAWL_BUDGET_S after they start; finished pages are kept."""

    async def say(step: str, status: str, **detail: Any) -> None:
        if report:
            await report(step, status, **detail)

    def cleaned(raw: list[str], into: dict[str, str]) -> None:
        for u in raw:
            if c := clean_url(u, url):
                into.setdefault(_key(c), c)

    await say("map", "running")
    mapping = (
        asyncio.create_task(map_site(http, url)) if settings.FIRECRAWL_API_KEY else None
    )
    try:
        sitemap = await asyncio.wait_for(
            sitemap_posts(url), settings.CRAWL_SITEMAP_WAIT_S
        )
    except TimeoutError:
        sitemap = []
    posts = {_key(p["url"]) for p in sitemap}
    if menu is None:
        menu = nav_links(home_html, url) if home_html else NO_MENU
    home_links = (
        [
            urljoin(url, a.attributes.get("href") or "")
            for a in LexborHTMLParser(home_html).css("a[href]")
        ]
        if home_html
        else []
    )
    found: dict[str, str] = {}
    cleaned([*menu.top, *home_links], found)  # menu first: the clinic's own order
    chosen, groups, mode = plan(list(found.values()), url, menu, posts)
    if via != "direct":
        chosen = chosen[: settings.FIRECRAWL_FALLBACKS]
    await say("pick", "done", total=len(chosen), mode=mode, groups=groups)

    await say("scrape", "running", total=len(chosen))
    read = _Reader(http, url, direct=via == "direct")
    sem = asyncio.Semaphore(settings.CRAWL_CONCURRENCY)
    started_reads = time.monotonic()

    async def one(u: str) -> tuple[str, str | None, str]:
        async with sem:  # FIFO: pages start in tier order, so a cut loses tier D first
            started = time.monotonic()
            html, how = await read(u)
            await say(
                f"page:{u}",
                "done" if html else "failed",
                url=u,
                ms=round((time.monotonic() - started) * 1000),
                via=how,
            )
            return u, html, how

    tasks = [asyncio.create_task(one(u)) for u in chosen]

    # Map runs while the menu pages are read. A slow map is dropped (the menu already gave
    # the services); a map error marks the audit partial, as a provider problem.
    ok, error, mapped = True, None, []
    if mapping:
        try:
            mapped = await asyncio.wait_for(mapping, settings.CRAWL_MAP_TIMEOUT_S)
        except (TimeoutError, httpx.TimeoutException):
            error = "Timed out"
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("site map failed for %s: %s", url, _why(exc))
            ok, error = False, _why(exc)
    cleaned(mapped, found)
    sources = {"map": len(mapped), "menu": len(menu.top), "home": len(home_links)}
    if error:
        await say("map", "failed", error=error, count=len(found), sources=sources)
    else:
        await say("map", "done", count=len(found), sources=sources)
    if mapped:
        more, groups, mode = plan(list(found.values()), url, menu, posts, chosen)
        extra = [u for u in more if u not in chosen]
        chosen += extra
        tasks += [asyncio.create_task(one(u)) for u in extra]
        await say("pick", "done", total=len(chosen), mode=mode, groups=groups)
        await say("scrape", "running", total=len(chosen))

    pending: set[asyncio.Task[tuple[str, str | None, str]]] = set()
    if tasks:
        left = max(settings.CRAWL_BUDGET_S - (time.monotonic() - started_reads), 0.01)
        _, pending = await asyncio.wait(tasks, timeout=left)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    results = [t.result() for t in tasks if t not in pending and t.exception() is None]
    pages = {u: h for u, h, _ in results if h}
    await say(
        "scrape",
        "done",
        ok=len(pages),
        failed=len(chosen) - len(pages),
        direct=sum(1 for u, h, how in results if h and how == "direct"),
        firecrawl=sum(1 for u, h, how in results if h and how == "firecrawl"),
        timed_out=len(pending),
    )
    return list(found.values()), pages, ok, sitemap


_MONTHS = {
    m: i
    for i, m in enumerate(
        (
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ),
        1,
    )
}
_MONTH = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_TEXT_DATES = (
    re.compile(
        _MONTH + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)", re.IGNORECASE
    ),  # October 10, 2026
    re.compile(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH + r"\.?,?\s+(20\d\d)", re.IGNORECASE
    ),  # 10 October 2026
)


def _text_date(text: str) -> str | None:
    """The first calendar date written out in `text` ("Oct 10, 2026" or "10 October 2026")."""
    for n, rx in enumerate(_TEXT_DATES):
        if m := rx.search(text):
            month, day, year = (
                (m.group(1), m.group(2), m.group(3))
                if n == 0
                else (m.group(2), m.group(1), m.group(3))
            )
            try:
                return date(int(year), _MONTHS[month[:3].lower()], int(day)).isoformat()
            except ValueError:
                return None
    return None


def _published(html: str) -> str | None:
    """When a post was published, from the page itself. In order of trust: page metadata
    (article:published_time, itemprop, name=date), a <time> tag, JSON-LD datePublished, and
    last a date written in the first part of the visible text (many themes print only that)."""
    doc = LexborHTMLParser(html)
    for sel in (
        'meta[property="article:published_time"]',
        'meta[property="og:article:published_time"]',
        'meta[itemprop="datePublished"]',
        'meta[name="date"]',
        "time[datetime]",
    ):
        node = doc.css_first(sel)
        if node:
            value = node.attributes.get("content") or node.attributes.get("datetime")
            if value and _age_days(value, datetime.now(UTC)) is not None:
                return str(value)[:25]
    for node in doc.css('script[type="application/ld+json"]'):
        found = re.search(r'"datePublished"\s*:\s*"([^"]+)"', node.text())
        if found and _age_days(found.group(1), datetime.now(UTC)) is not None:
            return found.group(1)[:25]
    for tag in doc.css("script, style, noscript, svg, nav, footer"):
        tag.decompose()
    body = doc.css_first("article") or doc.css_first("main") or doc.css_first("body")
    return (
        _text_date(" ".join(body.text(separator=" ", strip=True).split())[:4000])
        if body
        else None
    )


def _is_post(url: str, home: str) -> bool:
    path = urlsplit(url).path.strip("/")
    return (
        bool(path)
        and _host(url) == _host(home)
        and not NOT_POST.search(url)
        and not BLOG_INDEX.search(url)
    )


def index_posts(html: str, page_url: str) -> list[dict[str, Any]]:
    """Posts listed on a blog index page: each post card's heading link and its <time> date."""
    found: dict[str, dict[str, Any]] = {}
    for stamp in LexborHTMLParser(html).css("time[datetime]"):
        node = stamp.parent
        for _ in range(8):  # climb from the date to the post card that holds it
            if node is None:
                break
            link = node.css_first(
                'h1 a[href], h2 a[href], h3 a[href], h4 a[href], a[rel="bookmark"]'
            )
            if link:
                url = urljoin(page_url, link.attributes.get("href") or "")
                if _is_post(url, page_url) and url not in found:
                    found[url] = {
                        "url": url,
                        "title": " ".join(link.text(strip=True).split())[:200],
                        "published_at": str(stamp.attributes.get("datetime"))[:25],
                    }
                break
            node = node.parent
    return list(found.values())


def _posts_in_sitemap(xml: str, home: str, trusted: bool) -> list[dict[str, Any]]:
    """Posts listed in one sitemap, dated by <lastmod>. A post sitemap is trusted as it is; in a
    general sitemap only URLs under a blog-like path (/blog/<slug>) count."""
    posts = []
    for entry in re.findall(r"<url>(.*?)</url>", xml, re.DOTALL)[:MAX_POSTS]:
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", entry, re.DOTALL)
        changed = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", entry, re.DOTALL)
        url = html_lib.unescape(loc.group(1)) if loc else ""
        if not url or not _is_post(url, home):
            continue
        if not trusted and not (
            BLOG.search(url) and urlsplit(url).path.strip("/").count("/") >= 1
        ):
            continue
        posts.append(
            {
                "url": url,
                "title": url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title(),
                "published_at": changed.group(1)[:25] if changed else None,
            }
        )
    return posts


async def sitemap_posts(home: str) -> list[dict[str, Any]]:
    """Posts and their dates from the site's sitemaps: WordPress post sitemaps first, then
    sitemap.xml (and the child sitemaps of a sitemap index that look like post lists). The date
    is the sitemap's last change, which is the publish date unless the post was edited."""
    parts = urlsplit(home)
    base = f"{parts.scheme}://{parts.netloc}"
    left = SITEMAP_FETCHES

    async def get(url: str) -> str | None:
        nonlocal left
        if left <= 0 or _host(url) != _host(home):
            return None
        left -= 1
        try:
            xml, _ = await fetch_html(url, accept=("application/xml", "text/xml"))
        except AppError:
            return None
        return xml

    for path in (*POST_SITEMAPS, *GENERAL_SITEMAPS):
        xml = await get(base + path)
        if xml is None:
            continue
        if "<sitemapindex" in xml:
            children = [
                html_lib.unescape(m)
                for m in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, re.DOTALL)
                if re.search(r"post|blog|news|article", m, re.IGNORECASE)
            ][:3]
            for child in children:
                body = await get(child)
                posts = _posts_in_sitemap(body, home, trusted=True) if body else []
                if posts:
                    return posts
            continue
        posts = _posts_in_sitemap(xml, home, trusted=path in POST_SITEMAPS)
        if posts:
            return posts
    return []


DATE_FETCHES = 30  # post pages read to find publish dates, newest-looking first
DATE_CONCURRENCY = 6
DATE_BUDGET_S = 20.0


def _key(url: str) -> str:
    return url.rstrip("/").lower()


def _url_posts(urls: list[str], pages: dict[str, str]) -> list[dict[str, Any]]:
    """Posts that live under a blog-like path (/blog/<slug>), dated from any page we read."""
    return [
        {
            "url": u,
            "title": u.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title(),
            "published_at": _published(pages[u]) if u in pages else None,
        }
        for u in dict.fromkeys(urls)
        if BLOG.search(u)
        and urlsplit(u).path.strip("/").count("/") >= 1
        and not NOT_POST.search(u)
    ]


async def date_posts(posts: list[dict[str, Any]]) -> None:
    """Fill in `published_at` for posts that have none by reading their pages directly.

    The blog list and sitemap often carry no dates, but each post page does. At most
    DATE_FETCHES pages are read, DATE_CONCURRENCY at a time, within DATE_BUDGET_S seconds;
    whatever finishes in time is kept. Never raises."""
    todo = [p for p in posts if not p.get("published_at")][:DATE_FETCHES]
    sem = asyncio.Semaphore(DATE_CONCURRENCY)

    async def one(p: dict[str, Any]) -> None:
        async with sem:
            try:
                html, _ = await fetch_html(p["url"])
            except AppError:
                return
            p["published_at"] = _published(html)

    tasks = [asyncio.create_task(one(p)) for p in todo]
    if tasks:
        _, pending = await asyncio.wait(tasks, timeout=DATE_BUDGET_S)
        for t in pending:
            t.cancel()


async def blog_posts(
    http: httpx.AsyncClient,
    urls: list[str],
    pages: dict[str, str],
    home: str,
    sitemap: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Every post we can find, with dates. Sources, best first: the blog index page (post
    cards, in the site's own order), the post sitemap, then posts found by URL pattern. Posts
    still without a date get their page read (see date_posts). Many sites keep posts outside
    /blog/ or print no dates in lists, so no single source is enough. Never raises: on any
    error the list is just shorter."""
    found: list[dict[str, Any]] = []
    index = next((u for u in [*pages, *urls] if BLOG_INDEX.search(u)), None)
    if index:
        html = pages.get(index)
        if html is None:
            html, _ = await _Reader(http, home, direct=True)(index)
        if html:
            found += index_posts(html, index)
    # crawl() already read the sitemap (to keep posts out of the service pages)
    found += sitemap if sitemap is not None else await sitemap_posts(home)
    found += _url_posts(urls, pages)
    merged: dict[str, dict[str, Any]] = {}
    for p in found:
        have = merged.setdefault(_key(p["url"]), dict(p))
        if not have.get("published_at") and p.get("published_at"):
            have["published_at"] = p["published_at"]
    posts = list(merged.values())
    await date_posts(posts)
    return posts


def _age_days(published_at: str | None, now: datetime) -> int | None:
    try:
        return (now.date() - date.fromisoformat(str(published_at)[:10])).days
    except ValueError:
        return None


def enrich(
    sections: dict[str, Any],
    urls: list[str],
    pages: dict[str, str],
    extra_posts: list[dict[str, Any]] | None = None,
    menu: Menu = NO_MENU,
) -> None:
    """Rewrite `site` and widen `convert` using every mapped URL and the scraped pages.
    `menu` lets a trust page be found by its link text ("Cost" is the pricing page).
    `extra_posts` come from blog_posts(); earlier entries win when a URL repeats."""
    site, convert = sections["site"], sections["convert"]
    all_urls = list(dict.fromkeys([*urls, *pages]))

    clusters: dict[str, list[str]] = {}
    for u, label in menu.labels.items():
        if label["kind"] == "service" and label.get("name"):
            clusters.setdefault(str(label["name"])[:80], []).append(u)
    if not clusters:
        for u in all_urls:
            if name := _service_of(u):
                clusters.setdefault(name, []).append(u)
        for c in site["services"]["clusters"]:
            clusters.setdefault(c["service"], c["pages"])
    site["services"]["clusters"] = [
        {
            "service": name,
            "found": len(p),
            "expected": max(len(p), 3),
            "pages": p[:20],
            "topics_present": [],
            "topics_missing": [],
        }
        for name, p in clusters.items()
    ]
    site["services"]["cluster_pages_found"] = sum(len(p) for p in clusters.values())
    site["services"]["cluster_pages_expected"] = sum(
        c["expected"] for c in site["services"]["clusters"]
    )

    city_pages = [u for u in all_urls if CITY.search(u)]
    site["cities"].update(
        pages_found=len(city_pages),
        hub_page=any(
            re.search(r"/(locations?|service-areas?)/?$", u, re.IGNORECASE)
            for u in all_urls
        ),
        city_pages=city_pages[:50],
    )

    by_url: dict[str, dict[str, Any]] = {}
    for p in [
        *(extra_posts or []),
        *(
            {
                "url": u,
                "title": u.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title(),
                "published_at": _published(pages[u]) if u in pages else None,
            }
            for u in all_urls
            if BLOG.search(u)
            and urlsplit(u).path.strip("/").count("/") >= 1
            and not NOT_POST.search(u)
        ),
    ]:
        have = by_url.setdefault(p["url"].rstrip("/"), dict(p))
        if not have.get("published_at") and p.get("published_at"):
            have["published_at"] = p["published_at"]
    posts = [p["url"] for p in by_url.values()]
    dated = sorted(by_url.values(), key=lambda p: p["published_at"] or "", reverse=True)
    now = datetime.now(UTC)
    ages = [_age_days(p["published_at"], now) for p in dated]
    blog_index = next(
        (u for u in all_urls if BLOG_INDEX.search(u)),
        None,
    )
    site["blog"].update(
        url=blog_index or site["blog"].get("url"),
        post_count=len(posts),
        dated_posts=sum(1 for p in dated if p["published_at"]),
        last_post_at=next(
            (p["published_at"] for p in dated if p["published_at"]), None
        ),
        posts_last6_months=sum(1 for a in ages if a is not None and a <= 183),
        posts_last12_months=sum(1 for a in ages if a is not None and a <= 365),
        posts=dated[:20],
        links_to_services=any(
            _service_of(a.attributes.get("href") or "")
            for u in posts
            if u in pages
            for a in LexborHTMLParser(pages[u]).css("a[href]")
        ),
    )

    site["proof"].update(
        before_after_gallery=site["proof"]["before_after_gallery"]
        or any(PROOF["before_after"].search(u) for u in all_urls),
        testimonial_pages=sum(1 for u in all_urls if PROOF["testimonial"].search(u)),
        reviews_page=any(PROOF["reviews"].search(u) for u in all_urls),
        case_study_pages=sum(1 for u in all_urls if PROOF["case_study"].search(u)),
        video_testimonials=any(
            ("youtube.com/embed" in h or "player.vimeo.com" in h)
            and "testimonial" in h.lower()
            for h in pages.values()
        ),
    )
    site["trust"] = [
        {
            "key": key,
            "label": label,
            "status": "found" if hit else "missing",
            "url": hit,
        }
        for key, label, words in TRUST
        for hit in [
            next((u for u in all_urls if any(w in u.lower() for w in words)), None)
            or next((u for u in menu.top if _trust_key(u, menu) == key), None)
        ]
    ]
    faq = next((u for u, h in pages.items() if _has_faq(h)), None)
    if faq:
        site["trust"] = [
            {**t, "status": "found", "url": t["url"] or faq}
            if t["key"] == "faq_page"
            else t
            for t in site["trust"]
        ]
    site["placeholder_pages"] = [
        u for u, h in pages.items() if any(p in h.lower() for p in PLACEHOLDER_TEXT)
    ][:10]
    site["pages_crawled"] = len(pages) + 1

    html_all = " ".join(pages.values()).lower()
    if not convert.get("booking_platform"):
        convert["booking_platform"] = next(
            (n for m, n in BOOKING.items() if m in html_all), None
        )
    convert["online_booking"] = (
        bool(convert["booking_platform"]) or convert["online_booking"]
    )
    convert["chat_widget"] = convert.get("chat_widget") or next(
        (n for m, n in CHAT.items() if m in html_all), None
    )
    convert["financing_mentioned"] = (
        convert["financing_mentioned"] or "financing" in html_all
    )
    for check in convert["checks"]:
        if check["key"] == "online_booking" and convert["online_booking"]:
            check["status"] = "ok"


def _has_faq(html: str) -> bool:
    """True when the page has an FAQ heading or FAQPage structured data."""
    doc = LexborHTMLParser(html)
    return "faqpage" in html.lower() or any(
        re.search(r"faq|frequently asked", h.text(), re.IGNORECASE)
        for h in doc.css("h1, h2, h3, h4")
    )


def gbp_links(pages: dict[str, str]) -> tuple[bool, bool]:
    """Does the site link to its Google Business Profile, and to a "leave a review" page?

    Looks at every link on the pages we read (the footer on most sites). Links in
    pages we did not read are not seen, so a miss means "not found", not "not there".
    """

    def is_profile(href: str) -> bool:
        u = urlsplit(href)
        host = (u.hostname or "").lower().removeprefix("www.")
        return (
            host in ("maps.app.goo.gl", "g.page", "maps.google.com")
            or (host == "goo.gl" and u.path.startswith("/maps"))
            or (
                host in ("google.com", "search.google.com")
                and u.path.startswith(("/maps", "/local"))
            )
        )

    def is_review(href: str) -> bool:
        low = href.lower()
        return (
            "writereview" in low
            or "g.page/r/" in low
            or ("review" in low and is_profile(href))
        )

    hrefs = [
        a.attributes.get("href") or ""
        for html in pages.values()
        for a in LexborHTMLParser(html).css("a[href]")
    ]
    return any(map(is_profile, hrefs)), any(map(is_review, hrefs))


GBP_QUERIES = 3  # each query is one paid Apify run, so stop at the first match
_GENERIC_NAME = re.compile(
    r"^(home|welcome|untitled|all rights reserved)\b", re.IGNORECASE
)
_COPYRIGHT = re.compile(
    r"(?:©|&copy;|&#169;)\s*(?:20\d\d)?\s*(?:-\s*20\d\d)?\s*([A-Z][^.<|\n\\]{2,60}?)\s*(?:\.|\||<|&|\\|$)"
)


def brand_name(html: str) -> str | None:
    """The business name from the page itself: structured data, og:site_name, or the footer's
    "© 2026 Business Name" line. Used to search Google Maps by name, which finds the profile far
    more reliably than searching for the domain."""
    doc = LexborHTMLParser(html)
    for node in doc.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.text())
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            kind = str(item.get("@type") if isinstance(item, dict) else "")
            name = item.get("name") if isinstance(item, dict) else None
            if name and re.search(r"Business|Organization|Clinic|Medical|Spa", kind):
                return str(name).strip()[:80]
    og = doc.css_first('meta[property="og:site_name"]')
    if og and (value := (og.attributes.get("content") or "").strip()):
        return value[:80]
    for found in _COPYRIGHT.findall(html):
        name = html_lib.unescape(found).strip(" ,-")
        if len(name) >= 3 and not _GENERIC_NAME.match(name):
            return name[:80]
    return None


def gbp_queries(hints: dict[str, str], html: str, domain: str) -> list[str]:
    """Google Maps searches to try, best first: the CRM company name, the name found on the
    page, the phone number on the page, then the bare domain (the weakest: Maps matches it
    loosely and often returns unrelated businesses)."""
    candidates = [
        hints.get("name") or "",
        brand_name(html) or "",
        raw_phone(html) or "",
        domain,
    ]
    seen: set[str] = set()
    out = []
    for q in candidates:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:GBP_QUERIES]


def _digits(value: object) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())[-10:]


def _gbp_from(p: dict[str, Any], reason: str, tried: list[str]) -> dict[str, Any]:
    loc = p.get("location") or {}
    return {
        "matched": True,
        "match_reason": reason,
        "name": p.get("title"),
        "verified": None
        if p.get("claimThisBusiness") is None
        else not p["claimThisBusiness"],
        "primary_category": p.get("categoryName"),
        "categories": p.get("categories") or [],
        "rating": p.get("totalScore"),
        "review_count": p.get("reviewsCount"),
        "address": p.get("address"),
        "phone": p.get("phone"),
        "maps_url": p.get("url"),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "found_by": tried[-1],
        # filled in by the audit from the pages it read (see gbp_links)
        "website_links_to_gbp": False,
        "review_link_on_site": False,
    }


async def gbp_lookup(
    http: httpx.AsyncClient, queries: list[str], domain: str, phone: str | None = None
) -> tuple[dict[str, Any] | None, list[str]]:
    """Find the clinic's Google Business Profile with Apify's Google Maps actor.

    Tries each query in turn and stops at the first place that is the clinic: its website is the
    audited domain, or its phone number is the one on the site. Returns (profile or None, the
    queries that were run)."""
    tried: list[str] = []
    site_phone = _digits(phone)
    for query in queries[:GBP_QUERIES]:
        tried.append(query)
        r = await http.post(
            f"https://api.apify.com/v2/acts/{settings.APIFY_GMAPS_ACTOR_ID}/run-sync-get-dataset-items",
            params={"token": settings.APIFY_API_TOKEN},
            json={
                "searchStringsArray": [query],
                "maxCrawledPlacesPerSearch": 5,
                "language": "en",
            },
            timeout=120,
        )
        r.raise_for_status()
        items = r.json()
        for p in items if isinstance(items, list) else []:
            site = p.get("website") or ""
            by_site = bool(site) and _host(site) == domain
            by_phone = len(site_phone) == 10 and _digits(p.get("phone")) == site_phone
            if by_site or by_phone:
                reason = (
                    "website and phone match"
                    if by_site and by_phone
                    else ("website matches" if by_site else "phone matches")
                )
                return _gbp_from(p, reason, tried), tried
    return None, tried


async def _psi_run(http: httpx.AsyncClient, url: str, strategy: str) -> dict[str, Any]:
    """One PageSpeed Insights pass: Lighthouse scores (0-100) plus LCP and CLS."""
    r = await http.get(
        PAGESPEED,
        params=[
            ("url", url),
            ("key", settings.GOOGLE_PAGESPEED_API_KEY),
            ("strategy", strategy),
            ("category", "performance"),
            ("category", "seo"),
            ("category", "accessibility"),
            ("category", "best-practices"),
        ],
        timeout=120,  # PSI runs a real Lighthouse pass; 30-60s is normal
    )
    r.raise_for_status()
    lh = r.json()["lighthouseResult"]

    def score(key: str) -> int | None:
        value = (lh.get("categories", {}).get(key) or {}).get("score")
        return None if value is None else round(value * 100)

    def metric(key: str) -> float | None:
        return (lh.get("audits", {}).get(key) or {}).get("numericValue")

    lcp, cls = metric("largest-contentful-paint"), metric("cumulative-layout-shift")
    return {
        "performance": score("performance"),
        "seo": score("seo"),
        "accessibility": score("accessibility"),
        "best_practices": score("best-practices"),
        "lcp_ms": None if lcp is None else round(lcp),
        "cls": None if cls is None else round(cls, 3),
    }


async def pagespeed(http: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Mobile and desktop PageSpeed Insights for the `on_page.pagespeed` field.

    The flat keys are the mobile run (older audits and the UI read them); `desktop` is the same
    scores for the desktop run, or None when only that call failed. A mobile failure raises.
    """
    results = await asyncio.gather(
        _psi_run(http, url, "mobile"),
        _psi_run(http, url, "desktop"),
        return_exceptions=True,
    )
    mobile, failed = results
    if isinstance(mobile, BaseException):
        raise mobile
    desktop: dict[str, Any] | None = None
    if isinstance(failed, dict):
        desktop = failed
    elif not isinstance(failed, Exception):
        raise failed  # cancellation etc.
    else:
        # httpx error text embeds the request URL, which carries the API key: log class/status only
        status = (
            failed.response.status_code
            if isinstance(failed, httpx.HTTPStatusError)
            else None
        )
        logger.warning(
            "desktop PageSpeed failed: %s (status %s)", type(failed).__name__, status
        )
    return {
        "mobile_performance": mobile["performance"],
        "seo": mobile["seo"],
        "accessibility": mobile["accessibility"],
        "best_practices": mobile["best_practices"],
        "lcp_ms": mobile["lcp_ms"],
        "cls": mobile["cls"],
        "desktop": desktop,
    }
