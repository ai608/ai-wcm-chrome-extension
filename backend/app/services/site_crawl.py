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
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from selectolax.lexbor import LexborHTMLParser

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.site_audit import SERVICES, fetch_html, raw_phone

logger = logging.getLogger(__name__)

FIRECRAWL = "https://api.firecrawl.dev/v2"
PAGESPEED = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
MAX_URLS = 500
MAX_PAGES = 25
# ponytail: 4 parallel scrapes per audit; raise if Firecrawl plan allows more concurrency.
_SCRAPE_CONCURRENCY = 4

BOOKING = {
    "joinblvd.com": "Boulevard",
    "vagaro.com": "Vagaro",
    "mindbodyonline.com": "Mindbody",
    "zenoti.com": "Zenoti",
    "janeapp.com": "Jane",
    "acuityscheduling.com": "Acuity",
    "calendly.com": "Calendly",
    "squareup.com": "Square",
    "leadconnectorhq.com": "GoHighLevel",
    "msgsndr.com": "GoHighLevel",
    "setmore.com": "Setmore",
    "glossgenius.com": "GlossGenius",
}
CHAT = {
    "podium.com": "Podium",
    "birdeye.com": "Birdeye",
    "intercom": "Intercom",
    "tidio": "Tidio",
    "widgets.leadconnectorhq.com": "GHL chat",
    "livechatinc": "LiveChat",
}
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
TRUST = (
    ("about_page", "About page", ("/about",)),
    (
        "team_page",
        "Providers / team page",
        ("/team", "/providers", "/our-staff", "/meet-"),
    ),
    ("faq_page", "FAQ page", ("/faq",)),
    ("pricing_page", "Pricing page", ("/pricing", "/prices", "/price-list")),
    ("financing_page", "Financing page", ("/financing", "/payment-plans")),
    ("privacy_policy", "Privacy policy", ("/privacy",)),
)


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
    r = await http.post(
        f"{FIRECRAWL}/scrape",
        headers={"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"},
        json={"url": url, "formats": ["rawHtml"], "onlyMainContent": False},
        timeout=60,
    )
    if r.status_code >= 400:
        return None
    data = r.json().get("data") or {}
    html = data.get("rawHtml") or data.get("html")
    return html if isinstance(html, str) and html.strip() else None


PER_GROUP = max(3, MAX_PAGES // 5)

# Called as report(step_id, status, **detail); used to show the crawl live in the panel.
Report = Callable[..., Awaitable[None]]


def group_pages(urls: list[str], home: str) -> dict[str, list[str]]:
    """Sort mapped URLs into the five page groups, most useful group first, before any cut."""
    groups: dict[str, list[str]] = {
        "service": [],
        "city": [],
        "proof": [],
        "trust": [],
        "blog": [],
    }
    for u in urls:
        if u.rstrip("/") == home.rstrip("/"):
            continue
        if _service_of(u):
            groups["service"].append(u)
        elif CITY.search(u):
            groups["city"].append(u)
        elif any(p.search(u) for p in PROOF.values()):
            groups["proof"].append(u)
        elif any(w in u.lower() for _, _, words in TRUST for w in words):
            groups["trust"].append(u)
        elif BLOG_INDEX.search(u) or (
            BLOG.search(u) and urlsplit(u).path.strip("/").count("/") <= 1
        ):
            groups["blog"].append(u)
    # The blog index lists posts with dates, so it is always read first.
    groups["blog"].sort(key=lambda u: not BLOG_INDEX.search(u))
    return groups


def pick_pages(urls: list[str], home: str) -> list[str]:
    """Most useful pages first: services, cities, proof, trust, then the blog index."""
    picked: list[str] = []
    for b in group_pages(
        urls, home
    ).values():  # a few per group so none crowds out the rest
        picked += b[:PER_GROUP]
    return list(dict.fromkeys(picked))[:MAX_PAGES]


async def crawl(
    http: httpx.AsyncClient, url: str, report: Report | None = None
) -> tuple[list[str], dict[str, str]]:
    async def say(step: str, status: str, **detail: Any) -> None:
        if report:
            await report(step, status, **detail)

    await say("map", "running")
    urls = await map_site(http, url)
    await say("map", "done", count=len(urls))
    chosen = pick_pages(urls, url)
    keep = set(chosen)
    await say(
        "pick",
        "done",
        total=len(chosen),
        groups=[
            {
                "name": name,
                "found": len(b),
                "picked": [u for u in b[:PER_GROUP] if u in keep],
                "skipped": len(b) - len([u for u in b[:PER_GROUP] if u in keep]),
            }
            for name, b in group_pages(urls, url).items()
        ],
    )
    await say("scrape", "running", total=len(chosen))
    sem = asyncio.Semaphore(_SCRAPE_CONCURRENCY)

    async def one(u: str) -> tuple[str, str | None]:
        async with sem:
            started = time.monotonic()
            try:
                html = await scrape(http, u)
            except httpx.HTTPError:
                html = None
            await say(
                f"page:{u}",
                "done" if html else "failed",
                url=u,
                ms=round((time.monotonic() - started) * 1000),
            )
            return u, html

    results = await asyncio.gather(*(one(u) for u in chosen))
    pages = {u: h for u, h in results if h}
    await say("scrape", "done", ok=len(pages), failed=len(chosen) - len(pages))
    return urls, pages


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
    http: httpx.AsyncClient, urls: list[str], pages: dict[str, str], home: str
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
            try:
                html = await scrape(http, index)
            except httpx.HTTPError:
                html = None
        if html:
            found += index_posts(html, index)
    found += await sitemap_posts(home)
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
) -> None:
    """Rewrite `site` and widen `convert` using every mapped URL and the scraped pages.
    `extra_posts` come from blog_posts(); earlier entries win when a URL repeats."""
    site, convert = sections["site"], sections["convert"]
    all_urls = list(dict.fromkeys([*urls, *pages]))

    clusters: dict[str, list[str]] = {}
    for u in all_urls:
        if name := _service_of(u):
            clusters.setdefault(name, []).append(u)
    for c in site["services"][
        "clusters"
    ]:  # keep services only mentioned on the home page
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
            "status": "found"
            if (
                hit := next(
                    (u for u in all_urls if any(w in u.lower() for w in words)), None
                )
            )
            else "missing",
            "url": hit,
        }
        for key, label, words in TRUST
    ]
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
