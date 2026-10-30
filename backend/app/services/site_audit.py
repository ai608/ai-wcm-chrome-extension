import asyncio
import ipaddress
import re
import socket
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import orjson
from selectolax.lexbor import LexborHTMLParser

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.constants import (
    BOOKING,
    LOCAL_BUSINESS_TYPES,
    PLATFORMS,
    SERVICES,
    SOCIAL_HOSTS,
    TRUST,
)

MAX_HTML_BYTES = 3_000_000
SECTION_KEYS = (
    "overview",
    "business",
    "on_page",
    "schema",
    "site",
    "convert",
    "research",
)
# Share buttons, tracking pixels, embedded videos and widgets are not the clinic's profile.
OFFER = re.compile(
    r"(?<!\w)(specials|special (offers?|pricing|promotions?)|promotions?|promo|discounts?"
    r"|\d+% off|\$\d+ off|free consultation)(?!\w)",
    re.IGNORECASE,
)
TRACKER = re.compile(r"piwik|pixel|/tr\?|doubleclick|analytics|1x1", re.IGNORECASE)
_NOT_PROFILE = re.compile(
    r"/(tr|sharer|share|sharing|shareArticle|plugins|dialog|embed|watch|intent|hashtag|pixel)"
    r"(?:\.php)?(?:/|\?|$)|/p/|/reel/|/video/",
    re.IGNORECASE,
)


def raw_social(html: str, host: str) -> str | None:
    """A profile link for `host` found anywhere in the page source, including inside scripts.

    Many themes (Kajabi, Wix, ...) build the footer with JavaScript, so its links exist only as
    text inside a <script> and a plain HTML parse never sees them."""
    pattern = re.compile(
        r"https?:\\?/\\?/(?:www\.)?" + re.escape(host) + r"[^\s\"'<>\\)]*",
        re.IGNORECASE,
    )
    for raw in pattern.findall(html):
        url = str(raw).replace("\\/", "/")
        parts = urlsplit(url)
        if parts.path.strip("/") and not _NOT_PROFILE.search(url):
            return url
    return None


def raw_phone(html: str) -> str | None:
    """A phone number from any tel: link in the page source (also inside scripts)."""
    for found in re.findall(r"tel:\+?([\d\-\s().]{7,20})", html):
        digits = re.sub(r"\D", "", found)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) == 10:
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return None


def normalize_url(value: str) -> tuple[str, str]:
    value = value.strip()
    if not value:
        raise AppError(422, "invalid_url", "A website URL is required")
    if "://" not in value:
        value = "https://" + value
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError as exc:
        raise AppError(422, "invalid_url", "Invalid website URL") from exc
    if (
        parts.scheme not in ("http", "https")
        or not host
        or parts.username
        or parts.password
    ):
        raise AppError(422, "invalid_url", "Invalid website URL")
    expected_port = 443 if parts.scheme == "https" else 80
    if port not in (None, expected_port) or len(value) > 2048:
        raise AppError(422, "url_not_allowed", "This website address is not allowed")
    if (
        host == "localhost"
        or host.endswith((".local", ".internal", ".localhost", ".test"))
        or "." not in host
    ):
        raise AppError(422, "url_not_allowed", "This website address is not allowed")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise AppError(422, "url_not_allowed", "IP addresses are not allowed")
    if not re.fullmatch(r"[a-z0-9.-]+", host):
        raise AppError(422, "invalid_url", "Invalid website host")
    path = parts.path or "/"
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, parts.query, "")), host


async def _public_ip(host: str, port: int) -> str:
    try:
        answers = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise AppError(
            422, "site_unreachable", "Website could not be resolved"
        ) from exc
    addresses = {answer[4][0] for answer in answers}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise AppError(422, "url_not_allowed", "This website address is not allowed")
    return min(str(address) for address in addresses)


class TransientFetchError(AppError):
    """A fetch that failed in a way that can pass: timeout, connection reset, 429 or 5xx.
    A 403, 404, a non-HTML page or an unsafe address is not transient and is never retried."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(422, "site_unreachable", message)
        self.retry_after = retry_after


TRANSIENT_STATUS = (429, 500, 502, 503, 504)


async def fetch_html(
    url: str, accept: tuple[str, ...] = ("text/html",)
) -> tuple[str, str]:
    """GET a public page. One retry after a short wait when the failure may pass."""
    try:
        return await _fetch_once(url, accept)
    except TransientFetchError as exc:
        # Retry-After is honoured up to 5 s: a page worth waiting longer for can be skipped.
        await asyncio.sleep(min(exc.retry_after or settings.CRAWL_RETRY_DELAY_S, 5.0))
        return await _fetch_once(url, accept)


async def _fetch_once(
    url: str, accept: tuple[str, ...] = ("text/html",)
) -> tuple[str, str]:
    current = url
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
        for _ in range(6):
            current, host = normalize_url(current)
            parts = urlsplit(current)
            port = parts.port or (443 if parts.scheme == "https" else 80)
            ip = await _public_ip(host, port)
            address = f"[{ip}]" if ":" in ip else ip
            target = urlunsplit(
                (parts.scheme, f"{address}:{port}", parts.path, parts.query, "")
            )
            try:
                async with client.stream(
                    "GET",
                    target,
                    headers={
                        "Host": parts.netloc,
                        "User-Agent": "WCM-Audit/1.0",
                        "Accept": ", ".join(accept),
                    },
                    extensions={"sni_hostname": host},
                    timeout=httpx.Timeout(10.0),
                ) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise AppError(
                                422, "site_unreachable", "Invalid website redirect"
                            )
                        current = urljoin(current, location)
                        continue
                    if response.status_code in TRANSIENT_STATUS:
                        wait = response.headers.get("retry-after", "")
                        raise TransientFetchError(
                            "Website could not be fetched",
                            float(wait) if wait.isdigit() else None,
                        )
                    if response.status_code >= 400:
                        raise AppError(
                            422, "site_unreachable", "Website could not be fetched"
                        )
                    content_type = response.headers.get("content-type", "").lower()
                    if not any(kind in content_type for kind in accept):
                        raise AppError(
                            422, "site_unreachable", "Website did not return HTML"
                        )
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_HTML_BYTES:
                            raise AppError(
                                422, "site_unreachable", "Website page is too large"
                            )
                        chunks.append(chunk)
                    return b"".join(chunks).decode(
                        response.encoding or "utf-8", "replace"
                    ), current
            except httpx.HTTPError as exc:
                raise TransientFetchError("Website could not be fetched") from exc
    raise AppError(422, "site_unreachable", "Website redirected too many times")


def _text(node: Any) -> str:
    return " ".join(node.text(separator=" ", strip=True).split()) if node else ""


def _attr(node: Any, key: str) -> str:
    return (node.attributes.get(key) or "").strip() if node else ""


def _meta(doc: LexborHTMLParser, name: str) -> str:
    return _attr(doc.css_first(f'meta[name="{name}"]'), "content")


def _on_page(doc: LexborHTMLParser, url: str) -> dict[str, Any]:
    title = _text(doc.css_first("title"))
    description = _meta(doc, "description")
    h1s = doc.css("h1")
    images = [i for i in doc.css("img") if not TRACKER.search(_attr(i, "src"))][:100]
    links = []
    domain = urlsplit(url).hostname
    for node in doc.css("a[href]")[:200]:
        href = urljoin(url, _attr(node, "href"))
        if urlsplit(href).scheme not in ("http", "https"):
            continue
        links.append(
            {
                "href": href,
                "text": _text(node)[:160],
                "kind": "internal" if urlsplit(href).hostname == domain else "external",
                "nofollow": "nofollow" in _attr(node, "rel").lower().split(),
            }
        )
    image_items = [
        {
            # A data: URI holds the whole image; keep only its type, not the file.
            "src": src.split(",", 1)[0] + ","
            if (src := _attr(node, "src")).startswith("data:")
            else urljoin(url, src),
            "alt": node.attributes.get("alt"),
            "width": int(v) if (v := _attr(node, "width")).isdigit() else None,
            "height": int(v) if (v := _attr(node, "height")).isdigit() else None,
        }
        for node in images
    ]
    essentials = []
    for key, label, value, ok in (
        ("title", "Page title", title, bool(title)),
        ("meta_description", "Meta description", description, bool(description)),
        (
            "canonical",
            "Canonical URL",
            _attr(doc.css_first('link[rel="canonical"]'), "href"),
            bool(doc.css_first('link[rel="canonical"]')),
        ),
        (
            "robots",
            "Robots",
            _meta(doc, "robots") or "indexable",
            "noindex" not in _meta(doc, "robots").lower(),
        ),
        ("h1", "H1", _text(h1s[0]) if h1s else "", len(h1s) == 1),
        ("https", "HTTPS", urlsplit(url).scheme.upper(), url.startswith("https://")),
        (
            "language",
            "Language",
            _attr(doc.css_first("html"), "lang"),
            bool(_attr(doc.css_first("html"), "lang")),
        ),
        ("viewport", "Viewport", _meta(doc, "viewport"), bool(_meta(doc, "viewport"))),
        (
            "image_alts",
            "Image alt text",
            f"{len(images) - sum(not i['alt'] for i in image_items)}/{len(images)}",
            all(i["alt"] for i in image_items),
        ),
    ):
        essentials.append(
            {
                "key": key,
                "label": label,
                "value": value or "Missing",
                "status": "ok" if ok else "warn",
            }
        )
    headings = []
    for node in doc.css("h1,h2,h3,h4,h5,h6")[:100]:
        headings.append(
            {"level": int((node.tag or "h1")[1]), "text": _text(node)[:300]}
        )
    return {
        "essentials": essentials,
        "headings": {"h1_count": len(h1s), "outline": headings},
        "links": {
            "internal": sum(i["kind"] == "internal" for i in links),
            "external": sum(i["kind"] == "external" for i in links),
            "nofollow": sum(i["nofollow"] for i in links),
            "items": links,
        },
        "images": {
            "total": len(images),
            "missing_alt": sum(not i["alt"] for i in image_items),
            "lazy": sum(_attr(i, "loading") == "lazy" for i in images),
            "items": image_items,
        },
        "pagespeed": None,
    }


def _schema(doc: LexborHTMLParser) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    errors = 0
    raw = []
    for node in doc.css('script[type="application/ld+json"]')[:20]:
        body = node.text()
        raw.append(body[:10_000])
        try:
            data = orjson.loads(body)
        except orjson.JSONDecodeError:
            errors += 1
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entries_nested = entry.get("@graph")
            for item in entries_nested if isinstance(entries_nested, list) else [entry]:
                if isinstance(item, dict):
                    typ = item.get("@type", "Unknown")
                    blocks.append(
                        {
                            "type": ", ".join(typ)
                            if isinstance(typ, list)
                            else str(typ),
                            "present_props": [k for k in item if not k.startswith("@")][
                                :30
                            ],
                            "missing_recommended": [],
                        }
                    )
    types = " ".join(b["type"].lower() for b in blocks)
    return {
        "json_ld_count": len(raw),
        "parse_errors": errors,
        "has_local_business": any(
            t.strip().lower() in LOCAL_BUSINESS_TYPES
            for b in blocks
            for t in b["type"].split(",")
        ),
        "has_faq_page": "faqpage" in types,
        "has_review_markup": "review" in types,
        "blocks": blocks,
        "raw": "\n\n".join(raw)[:30_000],
    }


def _local_business(doc: LexborHTMLParser) -> dict[str, str]:
    """Name, address and phone from the page's LocalBusiness structured data or microdata."""
    for node in doc.css('script[type="application/ld+json"]')[:20]:
        try:
            data = orjson.loads(node.text())
        except orjson.JSONDecodeError:
            continue
        for entry in data if isinstance(data, list) else [data]:
            graph = entry.get("@graph") if isinstance(entry, dict) else None
            for item in graph if isinstance(graph, list) else [entry]:
                kinds = item.get("@type", []) if isinstance(item, dict) else []
                kinds = kinds if isinstance(kinds, list) else [kinds]
                if not LOCAL_BUSINESS_TYPES & {str(k).lower() for k in kinds}:
                    continue
                addr = item.get("address")
                if isinstance(addr, dict):
                    keys = (
                        "streetAddress",
                        "addressLocality",
                        "addressRegion",
                        "postalCode",
                    )
                    addr = ", ".join(str(addr[k]) for k in keys if addr.get(k))
                return {
                    "name": str(item.get("name") or ""),
                    "address": str(addr or ""),
                    "phone": str(item.get("telephone") or ""),
                }
    box = doc.css_first('[itemtype*="LocalBusiness"]')
    if box is None:
        return {}
    keys = ("streetAddress", "addressLocality", "addressRegion", "postalCode")
    parts = [_text(box.css_first(f'[itemprop="{k}"]')) for k in keys]
    return {
        "name": _text(box.css_first('[itemprop="name"]')),
        "address": ", ".join(p for p in parts if p),
        "phone": _text(box.css_first('[itemprop="telephone"]')),
    }


def empty_research() -> dict[str, Any]:
    blank = {"state": "not_run", "data": None, "error": None, "ran_at": None}
    return {
        "domain_overview": blank.copy(),
        "local_competitors": blank.copy(),
        "ai_visibility": blank.copy(),
    }


# Plain language issue copy. No em dashes. Short: what is wrong, why it costs calls.
ISSUE_COPY: dict[str, tuple[str, str]] = {
    "title": (
        "Page title needs work",
        "The browser tab and Google result look blank or vague, so fewer patients click through.",
    ),
    "meta_description": (
        "Meta description is missing",
        "Google shows random page text in results, which lowers clicks from search.",
    ),
    "canonical": (
        "No canonical URL is set",
        "Google may split ranking strength across duplicate page addresses.",
    ),
    "robots": (
        "Page may block search indexing",
        "A noindex setting would keep this page out of Google completely.",
    ),
    "h1": (
        "Main heading is unclear",
        "With zero or several H1s, patients and Google cannot tell what this page is about.",
    ),
    "https": (
        "Site does not use HTTPS",
        "Browsers warn visitors away from pages that are not secure.",
    ),
    "language": (
        "Page language is not declared",
        "Screen readers and Google cannot tell which language this page uses.",
    ),
    "viewport": (
        "Page may be hard to use on phones",
        "Without a mobile viewport, text and buttons can be tiny where most patients browse.",
    ),
    "image_alts": (
        "Some images miss alt text",
        "Missing alt text hurts image search and screen readers for visually impaired visitors.",
    ),
    "online_booking": (
        "No online booking found",
        "After hours visitors cannot book without calling, so many simply leave.",
    ),
    "click_to_call": (
        "No tap to call link",
        "Mobile visitors cannot call with one tap, which loses urgent treatment inquiries.",
    ),
    "contact_form": (
        "No contact form found",
        "Visitors have no quick way to ask about treatments without picking up the phone.",
    ),
}


def analyze(html: str, url: str, hints: dict[str, str] | None = None) -> dict[str, Any]:
    doc = LexborHTMLParser(html)
    on_page = _on_page(doc, url)
    schema = _schema(doc)
    visible = _text(doc.css_first("body")).lower()[:100_000]
    links = on_page["links"]["items"]
    internal = [i for i in links if i["kind"] == "internal"]
    site_urls = list(dict.fromkeys(i["href"] for i in internal))
    clusters: list[dict[str, Any]] = []
    for name, terms in SERVICES.items():
        matched = [
            i["href"]
            for i in internal
            if any(
                t in (i["href"] + " " + i["text"]).lower().replace("-", " ")
                for t in terms
            )
        ]
        matched = list(dict.fromkeys(matched))
        mentioned_on_home = any(
            re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", visible)
            for term in terms
        )
        if mentioned_on_home and not matched:
            matched = [url]
        if matched:
            clusters.append(
                {
                    "service": name,
                    "found": len(matched),
                    "expected": len(terms),
                    "pages": matched,
                    "topics_present": [],
                    "topics_missing": [],
                }
            )
    city_pages = [
        i["href"]
        for i in internal
        if re.search(
            r"/(locations?|service-areas?|areas-we-serve)/", i["href"], re.IGNORECASE
        )
    ]
    city_pages = list(dict.fromkeys(city_pages))
    socials = []
    for network, host in SOCIAL_HOSTS:
        match = next(
            (
                i["href"]
                for i in links
                if urlsplit(i["href"]).hostname in (host, "www." + host)
                and urlsplit(i["href"]).path.strip("/")
                and not _NOT_PROFILE.search(i["href"])
            ),
            None,
        ) or raw_social(html, host)
        if match:
            socials.append({"network": network, "url": match})
    phone = raw_phone(html) or next(
        (unescape(_text(i)) for i in doc.css('a[href^="tel:"]') if _text(i)), None
    )
    local = _local_business(doc)
    platform = next((name for name, marker in PLATFORMS if marker in html), None)
    site = {
        "platform": {"name": platform, "detail": None},
        "pages_crawled": 1,
        "services": {
            "cluster_pages_found": sum(c["found"] for c in clusters),
            "cluster_pages_expected": sum(c["expected"] for c in clusters),
            "clusters": clusters,
        },
        "cities": {
            "pages_found": len(city_pages),
            "hub_page": bool(city_pages),
            "city_pages": city_pages,
            "claimed_not_built": [],
        },
        "proof": {
            "before_after_gallery": "before and after" in visible,
            "testimonial_pages": sum("testimonial" in i for i in site_urls),
            "reviews_page": any("review" in i for i in site_urls),
            "case_study_pages": sum("case-stud" in i for i in site_urls),
            "video_testimonials": False,
        },
        "blog": {
            "url": next(
                (
                    i
                    for i in site_urls
                    if re.search(r"/(blogs?|news|articles)/?$", i, re.IGNORECASE)
                ),
                None,
            ),
            "post_count": 0,
            "dated_posts": 0,
            "last_post_at": None,
            "posts_last6_months": 0,
            "posts_last12_months": 0,
            "links_to_services": False,
            "posts": [],
        },
        "trust": [
            {
                "key": key,
                "label": label,
                "status": "found" if hit else "missing",
                "url": hit,
            }
            for key, label, words in TRUST
            for hit in [
                next((i for i in site_urls if any(w in i.lower() for w in words)), None)
            ]
        ],
    }
    lower = html.lower()
    booking = next((name for marker, name in BOOKING.items() if marker in lower), None)
    checks = [
        {
            "key": "online_booking",
            "label": "Online booking",
            "status": "ok" if booking else "warn",
        },
        {
            "key": "click_to_call",
            "label": "Click-to-call",
            "status": "ok" if doc.css_first('a[href^="tel:"]') else "warn",
        },
        {
            "key": "contact_form",
            "label": "Contact form",
            "status": "ok" if doc.css_first("form") else "warn",
        },
    ]
    convert = {
        "booking_platform": booking,
        "online_booking": bool(booking),
        "phone_in_header": bool(doc.css_first('header a[href^="tel:"]')),
        "click_to_call": bool(doc.css_first('a[href^="tel:"]')),
        "forms_count": len(doc.css("form")),
        "chat_widget": None,
        "cta_above_fold": False,
        "offers_or_specials": bool(OFFER.search(visible)),
        "financing_mentioned": "financing" in visible,
        "text_us": bool(doc.css_first('a[href^="sms:"]')),
        "checks": checks,
    }
    business = {
        "gbp": None,
        "company": None,
        "socials": socials,
        "nap": {
            "name": (hints.get("name") if hints else None) or local.get("name") or None,
            "address": local.get("address") or None,
            "phone": phone,
            "consistent_with_gbp": None,
        },
    }
    # The score needs the whole audit (crawl, AI, GBP, PageSpeed): site_score.compute
    # fills this in once the run has finished.
    overview: dict[str, Any] = {
        "score": None,
        "grade": None,
        "provisional": True,
        "provisional_reasons": [],
        "categories": [],
        "top_issues": [],
        "issue_count": 0,
        "warning_count": 0,
        "summary_text": "",
    }
    return {
        "overview": overview,
        "business": business,
        "on_page": on_page,
        "schema": schema,
        "site": site,
        "convert": convert,
        "research": empty_research(),
    }
