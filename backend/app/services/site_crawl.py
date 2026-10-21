"""Whole-site data for an audit: Firecrawl (map + scrape) and Apify (Google Business Profile).

site_audit.analyze() only sees the home page. This module adds the rest of the site to the
`site` and `convert` sections and fills `business.gbp`. Every provider call is optional:
without a key, or on any provider error, the home-page result is kept as it is.
"""

import asyncio
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from selectolax.lexbor import LexborHTMLParser

from app.core.config import settings
from app.services.site_audit import SERVICES

FIRECRAWL = "https://api.firecrawl.dev/v2"
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


def pick_pages(urls: list[str], home: str) -> list[str]:
    """Most useful pages first: services, cities, proof, trust, then the blog index."""
    buckets: list[list[str]] = [[], [], [], [], []]
    for u in urls:
        if u.rstrip("/") == home.rstrip("/"):
            continue
        if _service_of(u):
            buckets[0].append(u)
        elif CITY.search(u):
            buckets[1].append(u)
        elif any(p.search(u) for p in PROOF.values()):
            buckets[2].append(u)
        elif any(w in u.lower() for _, _, words in TRUST for w in words):
            buckets[3].append(u)
        elif BLOG.search(u) and urlsplit(u).path.strip("/").count("/") <= 1:
            buckets[4].append(u)
    picked: list[str] = []
    for b in buckets:  # round-robin so one huge bucket can't crowd out the rest
        picked += b[: max(3, MAX_PAGES // 5)]
    return list(dict.fromkeys(picked))[:MAX_PAGES]


async def crawl(http: httpx.AsyncClient, url: str) -> tuple[list[str], dict[str, str]]:
    urls = await map_site(http, url)
    sem = asyncio.Semaphore(_SCRAPE_CONCURRENCY)

    async def one(u: str) -> tuple[str, str | None]:
        async with sem:
            try:
                return u, await scrape(http, u)
            except httpx.HTTPError:
                return u, None

    results = await asyncio.gather(*(one(u) for u in pick_pages(urls, url)))
    return urls, {u: h for u, h in results if h}


def _published(html: str) -> str | None:
    doc = LexborHTMLParser(html)
    for sel in (
        'meta[property="article:published_time"]',
        'meta[name="date"]',
        "time[datetime]",
    ):
        node = doc.css_first(sel)
        if node:
            value = node.attributes.get("content") or node.attributes.get("datetime")
            if value:
                return str(value)[:25]
    return None


def enrich(sections: dict[str, Any], urls: list[str], pages: dict[str, str]) -> None:
    """Rewrite `site` and widen `convert` using every mapped URL and the scraped pages."""
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

    posts = [
        u
        for u in all_urls
        if BLOG.search(u) and urlsplit(u).path.strip("/").count("/") >= 1
    ]
    dated = sorted(
        (
            {
                "url": u,
                "title": u.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title(),
                "published_at": _published(pages[u]) if u in pages else None,
            }
            for u in posts
        ),
        key=lambda p: p["published_at"] or "",
        reverse=True,
    )
    blog_index = next(
        (
            u
            for u in all_urls
            if re.search(r"/(blog|blogs/news|news)/?$", u, re.IGNORECASE)
        ),
        None,
    )
    site["blog"].update(
        url=blog_index or site["blog"].get("url"),
        post_count=len(posts),
        last_post_at=next(
            (p["published_at"] for p in dated if p["published_at"]), None
        ),
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


async def gbp_lookup(
    http: httpx.AsyncClient, query: str, domain: str
) -> dict[str, Any] | None:
    """Find the clinic's Google Business Profile with Apify's Google Maps actor, matched by website."""
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
        if site and _host(site) == domain:
            loc = p.get("location") or {}
            return {
                "matched": True,
                "match_reason": "website matches",
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
                "website_links_to_gbp": False,
                "review_link_on_site": False,
            }
    return None
