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

from app.core.exceptions import AppError

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
SERVICES = {
    "Neurotoxins": ("botox", "dysport", "xeomin", "neurotoxin"),
    "Dermal Fillers": ("filler", "juvederm", "restylane"),
    "Medical Weight Loss": ("weight loss", "semaglutide", "tirzepatide", "glp-1"),
    "IV Therapy": ("iv therapy", "iv hydration", "nad+", "vitamin injection"),
    "Hormone Replacement": ("hormone", "hrt", "trt", "testosterone"),
    "Laser Hair Removal": ("laser hair removal",),
    "Microneedling": ("microneedling", "micro needling"),
    "Chemical Peels & Facials": ("chemical peel", "hydrafacial", "facial", "facials"),
    "Body Contouring": ("body contour", "coolsculpting", "emsculpt"),
    "PRP / Hair Restoration": ("prp", "hair restoration"),
    "Chiropractic": ("chiropractic", "chiropractor"),
    "Functional Medicine": ("functional medicine",),
}


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


async def fetch_html(url: str) -> tuple[str, str]:
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
                        "Accept": "text/html",
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
                    if response.status_code >= 400:
                        raise AppError(
                            422, "site_unreachable", "Website could not be fetched"
                        )
                    if (
                        "text/html"
                        not in response.headers.get("content-type", "").lower()
                    ):
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
                raise AppError(
                    422, "site_unreachable", "Website could not be fetched"
                ) from exc
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
    images = doc.css("img")[:100]
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
            "src": urljoin(url, _attr(node, "src")),
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
            t in types
            for t in (
                "localbusiness",
                "medicalbusiness",
                "medicalclinic",
                "day spa",
                "dayspa",
            )
        ),
        "has_faq_page": "faqpage" in types,
        "has_review_markup": "review" in types,
        "blocks": blocks,
        "raw": "\n\n".join(raw)[:30_000],
    }


def empty_research() -> dict[str, Any]:
    blank = {"state": "not_run", "data": None, "error": None, "ran_at": None}
    return {
        "domain_overview": blank.copy(),
        "local_competitors": blank.copy(),
        "ai_visibility": blank.copy(),
    }


def _grade_for(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _points(status: str) -> float | None:
    if status == "ok":
        return 1.0
    if status == "warn":
        return 0.5
    if status == "fail":
        return 0.0
    return None


def _score_checks(checks: list[dict[str, Any]]) -> int:
    total = 0.0
    scored = 0
    for item in checks:
        value = _points(str(item.get("status", "")))
        if value is None:
            continue
        total += value
        scored += 1
    if scored == 0:
        return 0
    return max(0, min(100, round(100 * total / scored)))


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
    domain = urlsplit(url).hostname or ""
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
    for network, host in (
        ("facebook", "facebook.com"),
        ("instagram", "instagram.com"),
        ("tiktok", "tiktok.com"),
        ("youtube", "youtube.com"),
        ("linkedin", "linkedin.com"),
        ("x", "x.com"),
    ):
        match = next(
            (
                i["href"]
                for i in links
                if urlsplit(i["href"]).hostname in (host, "www." + host)
            ),
            None,
        )
        if match:
            socials.append({"network": network, "url": match})
    phone = next(
        (unescape(_text(i)) for i in doc.css('a[href^="tel:"]') if _text(i)), None
    )
    platform = (
        "WordPress"
        if "wp-content/" in html
        else "Shopify"
        if "cdn.shopify.com" in html
        else None
    )
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
            "url": next((i for i in site_urls if re.search(r"/blog/?$", i)), None),
            "post_count": 0,
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
                "status": "found"
                if any(any(word in i for word in words) for i in site_urls)
                else "missing",
                "url": next(
                    (i for i in site_urls if any(word in i for word in words)), None
                ),
            }
            for key, label, words in (
                ("about_page", "About page", ("/about",)),
                ("faq_page", "FAQ page", ("/faq",)),
                ("pricing_page", "Pricing page", ("/pricing", "/prices")),
                ("privacy_policy", "Privacy policy", ("/privacy",)),
            )
        ],
    }
    booking = next(
        (
            name
            for name, marker in (
                ("Boulevard", "joinblvd.com"),
                ("Vagaro", "vagaro.com"),
                ("Mindbody", "mindbodyonline.com"),
                ("Zenoti", "zenoti.com"),
                ("Jane", "janeapp.com"),
                ("Calendly", "calendly.com"),
                ("Square", "squareup.com"),
            )
            if marker in html.lower()
        ),
        None,
    )
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
        "offers_or_specials": "special" in visible or "offer" in visible,
        "financing_mentioned": "financing" in visible,
        "text_us": bool(doc.css_first('a[href^="sms:"]')),
        "checks": checks,
    }
    business = {
        "gbp": None,
        "company": None,
        "socials": socials,
        "nap": {
            "name": hints.get("name") if hints else None,
            "address": None,
            "phone": phone,
            "consistent_with_gbp": None,
        },
    }
    essentials: list[dict[str, Any]] = on_page["essentials"]
    scored_all = [
        i for i in essentials + checks if _points(str(i.get("status"))) is not None
    ]
    total_points = sum(_points(str(i.get("status"))) or 0.0 for i in scored_all)
    score = (
        max(0, min(100, round(100 * total_points / len(scored_all))))
        if scored_all
        else 0
    )
    grade = _grade_for(score)
    fundamentals_score = _score_checks(essentials)
    convert_score = _score_checks(checks)
    categories = [
        {
            "key": "site_fundamentals",
            "label": "Site fundamentals",
            "grade": _grade_for(fundamentals_score),
            "score": fundamentals_score,
        },
        {
            "key": "getting_the_call",
            "label": "Getting the call",
            "grade": _grade_for(convert_score),
            "score": convert_score,
        },
    ]
    failures = [i for i in scored_all if str(i.get("status")) in ("warn", "fail")]
    warn_count = sum(1 for i in scored_all if str(i.get("status")) == "warn")
    top_issues = []
    for item in failures[:10]:
        key = str(item.get("key", ""))
        category = (
            "getting_the_call"
            if any(c.get("key") == key for c in checks)
            else "site_fundamentals"
        )
        copy = ISSUE_COPY.get(key)
        if copy is not None:
            title, detail = copy
        else:
            title = str(item.get("label", key)) + " needs attention"
            detail = str(item.get("value") or "Not found on the home page")
        top_issues.append({"category": category, "title": title, "detail": detail})
    overview = {
        "score": score,
        "grade": grade,
        "provisional": True,
        "categories": categories,
        "top_issues": top_issues,
        "issue_count": len(failures),
        "warning_count": warn_count,
        "summary_text": f"{domain}: {score}/100 based on home-page checks. {len(failures)} items need attention. GBP and company data were not assessed.",
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
