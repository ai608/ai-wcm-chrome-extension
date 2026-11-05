import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import orjson
from selectolax.lexbor import LexborHTMLParser

from app.services import crawl_access, onpage_more, site_crawl
from app.services.constants import (
    GENERIC_TITLES,
    LOCAL_BUSINESS_TYPES,
    REFERENCE_HOSTS,
    SCHEMA_PROPS,
    SERVICES,
)

CORE = frozenset({"home", "service", "menu_child", "hub", "hub_child"})
RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
WEIGHT = {"critical": 20, "high": 6, "medium": 3, "low": 0}
PER_KEY = 3
THIN_WORDS = 150
JS_WORDS = 100
JS_BYTES = 100_000
SHINGLE = 5
SHINGLE_WORDS = 600
SAME_TEXT = 0.85
MIN_TEXT_WORDS = 50
SHORT_TITLE = 15

GENERIC_ANCHOR = re.compile(
    r"^(click here|here|read more|learn more|more|view more|details|read on|see more)\W*$",
    re.IGNORECASE,
)
BAD_ALT = re.compile(
    r"^(image|photo|picture|img|graphic|banner|icon)\s*\d*$"
    r"|\.(jpe?g|png|webp|gif|avif|svg)$|^(img|dsc|screenshot)[-_ ]?\d+",
    re.IGNORECASE,
)
BAD_NAME = re.compile(
    r"^(img|dsc|dscn|image|photo|screenshot|untitled|unnamed)[-_ ]?\d*$|^\d+$|^[0-9a-f]{16,}$",
    re.IGNORECASE,
)
LEGACY = (".jpg", ".jpeg", ".png", ".gif")
CREDENTIALS = re.compile(
    r"\b(M\.?D\.?|D\.?O\.?|N\.?P\.?|FNP(-C)?|DNP|APRN|PA-C|R\.?N\.?|PharmD|D\.?C\.?|DPM|N\.?D\.?)\b"
)
REVIEWED_BY = re.compile(
    r"(medically\s+)?(reviewed|fact[- ]checked)\s+by", re.IGNORECASE
)
LAST_REVIEWED = re.compile(
    r"(last\s+)?(updated|reviewed)\s*[:\-]?\s*(on\s+)?"
    r"([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
DISCLAIMER = re.compile(
    r"results may vary|individual results|not intended to (diagnose|treat)|not medical advice"
    r"|consult (with )?(your|a) (doctor|physician|provider)",
    re.IGNORECASE,
)
HOURS = re.compile(
    r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*[-–:]?\s*\d{1,2}(:\d{2})?\s*(am|pm|a\.m\.|p\.m\.)",
    re.IGNORECASE,
)
YEAR = re.compile(r"\b(20\d{2})\b")
UGLY_URL = re.compile(r"[?&](p|page_id)=\d+|[A-Z]|_|/\d+/?$")

ISSUES: dict[str, tuple[str, str, str, str]] = {
    "no_title": (
        "high",
        "medium",
        "No page title",
        "Google has nothing to show as the blue link for this page.",
    ),
    "generic_title": (
        "high",
        "medium",
        "Title does not say what the page is",
        "Search results show this title. It should name the service and the city.",
    ),
    "short_title": (
        "low",
        "low",
        "Title is very short",
        "Add the service and the city.",
    ),
    "title_no_topic": (
        "low",
        "low",
        "Title does not name the service",
        "People who search for the treatment may not recognise this page.",
    ),
    "old_year_title": (
        "low",
        "low",
        "Title shows an old year",
        "Google may rewrite a title that looks out of date.",
    ),
    "duplicate_title": (
        "high",
        "medium",
        "Same title as {n} other page(s)",
        "Google cannot tell these pages apart, so it may show only one of them.",
    ),
    "no_description": (
        "low",
        "",
        "No meta description",
        "Google often writes its own, but a clear one helps on key pages.",
    ),
    "duplicate_description": (
        "low",
        "low",
        "Same description as {n} other page(s)",
        "Each page needs its own description.",
    ),
    "no_h1": (
        "high",
        "low",
        "No main heading (H1)",
        "The page does not say in one line what it is about.",
    ),
    "multiple_h1": (
        "low",
        "low",
        "{n} main headings (H1) on one page",
        "One clear main heading is simpler for visitors and for Google.",
    ),
    "noindex": (
        "critical",
        "low",
        "Google is told to hide this page",
        "A noindex tag removes the page from search results.",
    ),
    "canonical_other_page": (
        "high",
        "medium",
        "Canonical points to another page",
        "Google may drop this page and show the other one: {detail}",
    ),
    "canonical_other_host": (
        "high",
        "medium",
        "Canonical points to another website",
        "Google may drop this page and show the other site: {detail}",
    ),
    "canonical_relative": (
        "medium",
        "low",
        "Canonical is not a full address",
        "Use the full address, with https and the host name.",
    ),
    "canonical_missing": (
        "low",
        "low",
        "No canonical address",
        "A self-pointing canonical keeps duplicate addresses from splitting the page.",
    ),
    "thin_page": (
        "medium",
        "",
        "Very little text ({n} words)",
        "A short page has little to rank for and little to convince a patient.",
    ),
    "js_only": (
        "high",
        "low",
        "Page text is not in the page source",
        "This page draws its text with JavaScript, so a search check may see a nearly empty page.",
    ),
    "ugly_url": (
        "low",
        "low",
        "Address is not readable",
        "Words in the address (for example /botox) help visitors and Google.",
    ),
    "duplicate_text": (
        "high",
        "medium",
        "Text is nearly the same as another page",
        "Same-text pages compete with each other: {detail}",
    ),
}

SITE_ISSUES: dict[str, tuple[str, str, str]] = {
    "robots_unreachable": (
        "high",
        "robots.txt gives a server error",
        "When robots.txt fails with a server error, Google may stop crawling the whole site.",
    ),
    "robots_blocks_site": (
        "critical",
        "robots.txt blocks the whole site",
        "Google is told not to crawl any page, so none can rank.",
    ),
    "robots_blocks_pages": (
        "high",
        "robots.txt blocks {detail} service or main pages",
        "Google cannot read a blocked page, so it cannot rank for what the page says.",
    ),
    "robots_blocks_assets": (
        "medium",
        "robots.txt blocks {detail} style or script files of the home page",
        "Google needs these files to see the page the way a visitor does.",
    ),
    "sitemap_missing": (
        "medium",
        "No sitemap found",
        "A sitemap lists every page you want found. Google can use it to find pages faster.",
    ),
    "sitemap_broken": (
        "high",
        "The sitemap in robots.txt cannot be read",
        "Google cannot use a sitemap that fails or is not valid XML.",
    ),
    "sitemap_not_in_robots": (
        "low",
        "robots.txt does not point to the sitemap",
        "A Sitemap line in robots.txt lets every search engine find it.",
    ),
    "sitemap_missing_pages": (
        "medium",
        "{detail} service or main pages are not in the sitemap",
        "Add every page that should rank, so Google finds it even without a link.",
    ),
    "sitemap_bad_urls": (
        "high",
        "{detail} sitemap pages are noindex or point to another page",
        "A sitemap should list only pages you want in search results.",
    ),
    "sitemap_blocked": (
        "high",
        "{detail} sitemap pages are blocked by robots.txt",
        "The sitemap asks Google to crawl pages that robots.txt forbids.",
    ),
    "schema_missing_required": (
        "high",
        "Business markup lacks {detail}",
        "Google needs these fields to understand the business.",
    ),
    "schema_missing_recommended": (
        "medium",
        "Business markup lacks {detail}",
        "These fields feed the Google result: hours, phone, map position.",
    ),
    "schema_generic_type": (
        "low",
        "Business markup uses a generic type",
        "A more exact type such as MedicalClinic tells Google what kind of business this is.",
    ),
    "schema_self_serving_review": (
        "high",
        "Review stars in the business's own markup",
        "Google does not allow a business to give itself review stars, and may act on it.",
    ),
    "schema_conflict": (
        "medium",
        "Business markup shows different phone numbers",
        "Conflicting data lowers trust in the listing.",
    ),
    "trust_no_credentials": (
        "medium",
        "No provider credentials found",
        "Health pages should show who treats the patient and their qualifications.",
    ),
    "trust_no_reviewer": (
        "low",
        "No reviewed-by line or review date",
        "Google looks for expert review and fresh information on health pages.",
    ),
    "trust_no_references": (
        "low",
        "No links to health sources",
        "Claims backed by a source build trust.",
    ),
    "trust_no_disclaimer": (
        "low",
        "No results disclaimer",
        "Before-and-after and results claims need a plain disclaimer.",
    ),
    "anchors_generic": (
        "medium",
        "{detail} links say only 'learn more' or 'click here'",
        "Link text tells Google what the target page is about.",
    ),
    "anchors_empty": (
        "medium",
        "{detail} links have no text",
        "A link with no text gives Google and screen readers nothing to read.",
    ),
    "links_not_crawlable": (
        "medium",
        "{detail} links cannot be followed by Google",
        "Google only follows real links (an a tag with an address).",
    ),
    "orphan_pages": (
        "medium",
        "{detail} service pages are not linked from the home page or menu",
        "A page nobody links to is hard for Google and patients to find.",
    ),
    "images_lazy_first": (
        "medium",
        "The first large image loads late",
        "A lazy first image slows the page that visitors see first.",
    ),
    "images_bad_alt": (
        "low",
        "{detail} images have unhelpful alt text",
        "Alt text should describe the picture, not repeat 'image' or a file name.",
    ),
    "images_bad_names": (
        "low",
        "{detail} image files have meaningless names",
        "Names such as botox-injection.jpg give Google a small clue.",
    ),
    "images_legacy": (
        "low",
        "Most images use older file formats",
        "WebP or AVIF files are smaller and load faster.",
    ),
    "local_no_map": (
        "low",
        "No map on the home page",
        "A map and written directions help local visitors.",
    ),
    "local_no_hours": (
        "low",
        "Opening hours are not written on the home page",
        "Patients look for hours before they call.",
    ),
}


def _parse(html: str) -> LexborHTMLParser:
    doc = LexborHTMLParser(html)
    for tag in doc.css("script, style, noscript"):
        tag.decompose()
    return doc


def _flat(node: Any) -> str:
    return " ".join(node.text(separator=" ", strip=True).split()) if node else ""


def _attr(node: Any, key: str) -> str:
    return (node.attributes.get(key) or "").strip() if node else ""


def _meta(doc: LexborHTMLParser, name: str) -> str:
    return _attr(doc.css_first(f'meta[name="{name}"]'), "content")


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _path(url: str) -> str:
    return urlsplit(url).path.rstrip("/") or "/"


def _issue(key: str, core: bool, url: str | None, **ctx: Any) -> dict[str, Any] | None:
    hi, lo, title, detail = ISSUES[key]
    severity = hi if core else lo
    if not severity:
        return None
    return {
        "key": key,
        "severity": severity,
        "title": title.format(**ctx),
        "detail": detail.format(**ctx),
        "url": url,
    }


def _canonical(doc: LexborHTMLParser, url: str) -> dict[str, str | None]:
    href = _attr(doc.css_first('link[rel="canonical"]'), "href")
    if not href:
        return {"url": None, "status": "missing"}
    if not urlsplit(href).scheme:
        return {"url": href, "status": "relative"}
    if "#" in href:
        return {"url": href, "status": "fragment"}
    if _host(href) != _host(url):
        return {"url": href, "status": "other_host"}
    if _path(href) != _path(url):
        return {"url": href, "status": "other_page"}
    return {"url": href, "status": "ok"}


def _terms(url: str) -> set[str]:
    slug = urlsplit(url).path.lower().replace("-", " ").replace("_", " ")
    name = site_crawl._service_of(url)
    return {w for w in slug.split("/")[-1].split() if len(w) > 3} | (
        {t for t in SERVICES.get(name or "", ())} if name else set()
    )


def analyze_page(
    html: str, url: str, kind: str, fetched: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Title, description, headings, indexing and text facts of one page, with its issues.
    `fetched` is what reading the URL revealed (redirects, X-Robots-Tag; see fetchlog)."""
    doc = _parse(html)
    core = kind in CORE
    title = _flat(doc.css_first("title"))
    description = _meta(doc, "description")
    h1s = doc.css("h1")
    robots = f"{_meta(doc, 'robots')} {_meta(doc, 'googlebot')}".lower()
    body = _flat(doc.css_first("body"))
    words = len(body.split())
    canonical = _canonical(doc, url)
    page = {
        "url": url,
        "kind": kind,
        "title": title,
        "title_len": len(title),
        "meta_description": description,
        "h1": _flat(h1s[0]) if h1s else "",
        "h1_count": len(h1s),
        "word_count": words,
        "noindex": "noindex" in robots,
        "canonical": canonical,
    }
    found: list[dict[str, Any] | None] = []
    if not title:
        found.append(_issue("no_title", core, url))
    elif title.lower().strip(" |-") in GENERIC_TITLES:
        found.append(_issue("generic_title", core, url))
    elif len(title) < SHORT_TITLE:
        found.append(_issue("short_title", core, url))
    if title and kind in ("service", "menu_child", "hub_child"):
        low = title.lower()
        if not any(t in low for t in _terms(url)):
            found.append(_issue("title_no_topic", core, url))
    if title and any(int(y) < datetime.now(UTC).year for y in YEAR.findall(title)):
        found.append(_issue("old_year_title", core, url))
    if not description:
        found.append(_issue("no_description", core, url))
    if not h1s:
        found.append(_issue("no_h1", core, url))
    elif len(h1s) > 1:
        found.append(_issue("multiple_h1", core, url, n=len(h1s)))
    if page["noindex"]:
        found.append(_issue("noindex", core, url))
    status = canonical["status"]
    if status in ("other_page", "other_host", "relative", "missing"):
        key = "canonical_" + str(status)
        found.append(_issue(key, core, url, detail=canonical["url"] or ""))
    if kind in ("service", "menu_child", "hub_child") and words < THIN_WORDS:
        found.append(_issue("thin_page", core, url, n=words))
    if words < JS_WORDS and len(html) > JS_BYTES:
        found.append(_issue("js_only", core, url))
    if UGLY_URL.search(urlsplit(url).path + ("?" + (urlsplit(url).query or ""))):
        found.append(_issue("ugly_url", core, url))
    found += onpage_more.page_checks(
        html,
        url,
        title=title,
        h1=_flat(h1s[0]) if h1s else "",
        text=body,
        core=core,
        has_disclaimer=bool(DISCLAIMER.search(body)),
        fetched=fetched,
    )
    page["issues"] = [i for i in found if i]
    page["_text"] = body
    return page


def _shingles(text: str) -> set[int]:
    words = text.lower().split()[:SHINGLE_WORDS]
    return {
        int(hashlib.md5(" ".join(words[i : i + SHINGLE]).encode()).hexdigest()[:12], 16)
        for i in range(max(len(words) - SHINGLE + 1, 0))
    }


def _duplicates(pages: list[dict[str, Any]]) -> dict[str, list[list[str]]]:
    out: dict[str, list[list[str]]] = {"titles": [], "descriptions": [], "text": []}
    for field, key in (("title", "titles"), ("meta_description", "descriptions")):
        groups: dict[str, list[str]] = {}
        for p in pages:
            if p[field].strip():
                groups.setdefault(p[field].strip().lower(), []).append(p["url"])
        out[key] = [urls for urls in groups.values() if len(urls) > 1]
    body = [
        (p["url"], _shingles(p["_text"]))
        for p in pages
        if p["kind"] in CORE and p["word_count"] >= MIN_TEXT_WORDS
    ]
    for i, (a, sa) in enumerate(body):
        for b, sb in body[i + 1 :]:
            if sa and sb and len(sa & sb) / len(sa | sb) >= SAME_TEXT:
                out["text"].append([a, b])
    return out


def _add_duplicate_issues(
    pages: list[dict[str, Any]], dups: dict[str, list[list[str]]]
) -> None:
    by_url = {p["url"]: p for p in pages}
    for key, issue in (
        ("titles", "duplicate_title"),
        ("descriptions", "duplicate_description"),
    ):
        for group in dups[key]:
            for u in group:
                p = by_url[u]
                new = _issue(issue, p["kind"] in CORE, u, n=len(group) - 1)
                if new:
                    p["issues"].append(new)
    for a, b in dups["text"]:
        for u, other in ((a, b), (b, a)):
            p = by_url[u]
            new = _issue("duplicate_text", p["kind"] in CORE, u, detail=other)
            if new:
                p["issues"].append(new)


SITE_ISSUES.update(onpage_more.SITE_ISSUES)


def _site_issue(key: str, detail: str = "") -> dict[str, Any]:
    severity, title, why = SITE_ISSUES[key]
    return {
        "key": key,
        "severity": severity,
        "title": title.format(detail=detail),
        "detail": why,
        "url": None,
    }


def _jsonld(doc: LexborHTMLParser) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for node in doc.css('script[type="application/ld+json"]')[:20]:
        try:
            data = orjson.loads(node.text())
        except orjson.JSONDecodeError:
            continue
        for entry in data if isinstance(data, list) else [data]:
            graph = entry.get("@graph") if isinstance(entry, dict) else None
            items += [
                x
                for x in (graph if isinstance(graph, list) else [entry])
                if isinstance(x, dict)
            ]
    return items


def _types(item: dict[str, Any]) -> list[str]:
    raw = item.get("@type", [])
    return [str(t) for t in (raw if isinstance(raw, list) else [raw])]


def _has(item: dict[str, Any], prop: str) -> bool:
    return bool(item.get(prop))


def schema_checks(sections: dict[str, Any], html: str) -> list[dict[str, Any]]:
    """Fill each schema block's missing properties and risks; return the site-level issues."""
    schema = sections.get("schema")
    if not schema:
        return []
    items = _jsonld(LexborHTMLParser(html))
    issues: list[dict[str, Any]] = []
    blocks = []
    risks: list[str] = []
    phones: set[str] = set()
    local_types: list[str] = []
    local_items: list[dict[str, Any]] = []
    for item in items:
        low = {t.lower() for t in _types(item)}
        row = (
            "local"
            if low & LOCAL_BUSINESS_TYPES
            else next((k for k in SCHEMA_PROPS if k in low), "")
        )
        required, recommended = SCHEMA_PROPS.get(row, ((), ()))
        missing_required = [p for p in required if not _has(item, p)]
        missing = [p for p in recommended if not _has(item, p)]
        blocks.append(
            {
                "type": ", ".join(_types(item)) or "Unknown",
                "present_props": [k for k in item if not k.startswith("@")][:30],
                "missing_required": missing_required,
                "missing_recommended": missing,
            }
        )
        if row == "local":
            local_items.append(item)
            local_types += [
                t for t in _types(item) if t.lower() in LOCAL_BUSINESS_TYPES
            ]
            if item.get("telephone"):
                phones.add(
                    "".join(c for c in str(item["telephone"]) if c.isdigit())[-10:]
                )
        if row in ("local", "organization") and (
            item.get("aggregateRating") or item.get("review")
        ):
            risks.append("self_serving_review")
    if local_items:
        required, recommended = SCHEMA_PROPS["local"]
        lacking = [p for p in required if not any(_has(i, p) for i in local_items)]
        missing = [p for p in recommended if not any(_has(i, p) for i in local_items)]
        if lacking:
            issues.append(_site_issue("schema_missing_required", ", ".join(lacking)))
        if missing:
            issues.append(
                _site_issue("schema_missing_recommended", ", ".join(missing[:4]))
            )
    if len(phones) > 1:
        issues.append(_site_issue("schema_conflict"))
    if local_types and {t.lower() for t in local_types} == {"localbusiness"}:
        issues.append(_site_issue("schema_generic_type"))
    if "self_serving_review" in risks:
        issues.append(_site_issue("schema_self_serving_review"))
    if blocks:
        schema["blocks"] = blocks
    schema["risks"] = sorted(set(risks))
    schema["local_business_type"] = local_types[0] if local_types else None
    return issues


def _filename(src: str) -> str:
    return urlsplit(src).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _home_checks(
    html: str, home: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    doc = LexborHTMLParser(html)
    for tag in doc.css("script, style, noscript"):
        tag.decompose()
    links = doc.css("a[href], a:not([href])")
    generic = empty = dead = 0
    for a in links:
        href = _attr(a, "href")
        text = _flat(a) or _attr(a, "aria-label") or _attr(a, "title")
        img = a.css_first("img")
        if href.lower().startswith("javascript:") or (not href and _attr(a, "onclick")):
            dead += 1
            continue
        if not href or href.startswith("#"):
            continue
        if not text and not (img is not None and _attr(img, "alt")):
            empty += 1
        elif GENERIC_ANCHOR.match(text):
            generic += 1
    images = [
        i
        for i in doc.css("img")
        if _attr(i, "src") and not _attr(i, "src").startswith("data:")
    ]
    alts = [_attr(i, "alt") for i in images]
    bad_alt = sum(1 for a in alts if a and BAD_ALT.search(a))
    bad_names = sum(1 for i in images if BAD_NAME.match(_filename(_attr(i, "src"))))
    legacy = sum(
        1 for i in images if urlsplit(_attr(i, "src")).path.lower().endswith(LEGACY)
    )
    first = next(
        (
            i
            for i in images
            if _attr(i, "width").isdigit() and int(_attr(i, "width")) >= 300
        ),
        None,
    )
    first_lazy = first is not None and _attr(first, "loading") == "lazy"
    text = _flat(doc.css_first("body"))
    link_info = {
        "generic_anchor_count": generic,
        "empty_anchor_count": empty,
        "not_crawlable_count": dead,
    }
    image_info = {
        "bad_alt": bad_alt,
        "bad_names": bad_names,
        "legacy_format": legacy,
        "first_image_lazy": first_lazy,
    }
    map_embed = bool(
        doc.css_first('iframe[src*="google.com/maps"], iframe[src*="maps.google"]')
    )
    local = {"map_embed": map_embed, "hours_text": bool(HOURS.search(text))}
    issues: list[dict[str, Any]] = []
    if generic >= 3:
        issues.append(_site_issue("anchors_generic", str(generic)))
    if empty:
        issues.append(_site_issue("anchors_empty", str(empty)))
    if dead:
        issues.append(_site_issue("links_not_crawlable", str(dead)))
    if first_lazy:
        issues.append(_site_issue("images_lazy_first"))
    if bad_alt:
        issues.append(_site_issue("images_bad_alt", str(bad_alt)))
    if images and bad_names * 2 >= len(images):
        issues.append(_site_issue("images_bad_names", str(bad_names)))
    if images and legacy * 10 >= len(images) * 8 and len(images) >= 5:
        issues.append(_site_issue("images_legacy"))
    if not map_embed:
        issues.append(_site_issue("local_no_map"))
    if not local["hours_text"]:
        issues.append(_site_issue("local_no_hours"))
    return link_info, image_info, local, issues


def _internal_links(html: str, base: str) -> set[str]:
    doc = LexborHTMLParser(html)
    out = set()
    for a in doc.css("a[href]"):
        url = site_crawl.clean_url(urljoin(base, _attr(a, "href")), base)
        if url:
            out.add(site_crawl._key(url))
    return out


def _trust(
    pages: dict[str, str], parsed: list[dict[str, Any]], home_html: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    credentials, reviewed, dated, disclaimers = [], [], [], []
    refs = 0
    for p in parsed:
        text = p["_text"]
        if p["kind"] in CORE or p["kind"] == "trust":
            if CREDENTIALS.search(text):
                credentials.append(p["url"])
            if DISCLAIMER.search(text):
                disclaimers.append(p["url"])
        if REVIEWED_BY.search(text):
            reviewed.append(p["url"])
        if LAST_REVIEWED.search(text):
            dated.append(p["url"])
    for html in pages.values():
        for a in LexborHTMLParser(html).css('a[href^="http"]'):
            host = _host(_attr(a, "href"))
            refs += any(host.endswith(h) or h in host for h in REFERENCE_HOSTS)
    has_terms = bool(
        re.search(r"/terms|terms-(of|and)|terms_", home_html, re.IGNORECASE)
    )
    info = {
        "credentials_pages": credentials[:10],
        "reviewed_by_pages": reviewed[:10],
        "dated_pages": dated[:10],
        "disclaimer_pages": disclaimers[:10],
        "reference_links": refs,
        "has_terms": has_terms,
    }
    issues = []
    if not credentials:
        issues.append(_site_issue("trust_no_credentials"))
    if not reviewed and not dated:
        issues.append(_site_issue("trust_no_reviewer"))
    if not refs:
        issues.append(_site_issue("trust_no_references"))
    if not disclaimers:
        issues.append(_site_issue("trust_no_disclaimer"))
    return info, issues


def _summary(issues: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for i in issues:
        g = groups.setdefault(i["key"], {**i, "count": 0, "pages": []})
        g["count"] += 1
        if i["url"] and len(g["pages"]) < 5:
            g["pages"].append(i["url"])
    counts = {s: sum(1 for i in issues if i["severity"] == s) for s in RANK}
    penalty = sum(
        WEIGHT[g["severity"]] * (1 + 0.5 * (min(g["count"], PER_KEY) - 1))
        for g in groups.values()
    )
    top = sorted(groups.values(), key=lambda g: (RANK[g["severity"]], -g["count"]))[:8]
    return {
        "score": max(0, round(100 - penalty)),
        **counts,
        "top_fixes": [
            {k: g[k] for k in ("key", "severity", "title", "detail", "count", "pages")}
            for g in top
            if g["severity"] != "low"
        ],
    }


def _probe_summary(probes: dict[str, Any] | None) -> dict[str, Any]:
    """What the extra requests did, for the panel. `ran` is False when they were skipped."""
    if not probes:
        return {"ran": False, "checked": 0, "timed_out": 0, "hosts": []}
    return {
        "ran": True,
        "checked": probes.get("checked", 0),
        "timed_out": probes.get("timed_out", 0),
        "hosts": [
            {k: h.get(k) for k in ("url", "status", "final", "hops")}
            for h in probes.get("hosts", [])
        ],
    }


SPEED_KEYS = frozenset(
    {
        "tap_targets_small",
        "viewport_blocks_zoom",
        "field_lcp_poor",
        "field_inp_poor",
        "field_cls_poor",
    }
)


def add_speed_issues(sections: dict[str, Any]) -> None:
    """Add what PageSpeed says about phones and real visitors to the issues, and score again.
    PageSpeed runs next to the page checks and finishes at its own time, so this is called once
    both are done. Calling it twice does not duplicate anything."""
    on_page = sections.get("on_page") or {}
    if "summary" not in on_page:
        return
    kept = [i for i in on_page.get("site_issues", []) if i["key"] not in SPEED_KEYS]
    on_page["site_issues"] = kept + onpage_more.speed_issues(on_page.get("pagespeed"))
    page_issues = [i for p in on_page.get("pages", []) for i in p["issues"]]
    on_page["summary"] = _summary(page_issues + on_page["site_issues"])


def run(
    sections: dict[str, Any],
    home: str,
    pages: dict[str, str],
    urls: list[str],
    menu: site_crawl.Menu,
    access: dict[str, Any] | None = None,
    fetched: dict[str, dict[str, Any]] | None = None,
    probes: dict[str, Any] | None = None,
) -> None:
    """Add the per-page checks, duplicates, trust, local, schema, link, structure and image checks
    to `sections`. `fetched` is what reading the pages revealed and `probes` the extra requests
    (`probes.run`); either may be absent, and the checks that need it are then skipped."""
    on_page = sections["on_page"]
    home_html = pages[home]
    parsed = []
    for url, html in pages.items():
        kind = (
            "home"
            if _path(url) == _path(home) and _host(url) == _host(home)
            else site_crawl.classify(url, menu)
        )
        parsed.append(analyze_page(html, url, kind, (fetched or {}).get(url)))
    dups = _duplicates(parsed)
    _add_duplicate_issues(parsed, dups)
    link_info, image_info, local, issues = _home_checks(home_html, home)
    trust, trust_issues = _trust(pages, parsed, home_html)
    linked = _internal_links(home_html, home) | {site_crawl._key(u) for u in menu.top}
    orphans = [
        u
        for u in urls
        if site_crawl.classify(u, menu) in ("service", "menu_child", "hub_child")
        and site_crawl._under_hub(u)
        and site_crawl._key(u) not in linked
        and site_crawl._key(u) != site_crawl._key(home)
    ]
    if orphans:
        issues.append(_site_issue("orphan_pages", str(len(orphans))))
    issues += trust_issues + schema_checks(sections, home_html)
    kinds = {p["url"]: p["kind"] for p in parsed}
    home_text = next((p["_text"] for p in parsed if p["kind"] == "home"), "")
    service = [p for p in parsed if p["kind"] in ("service", "menu_child", "hub_child")]
    link_check, link_issues = onpage_more.link_checks(fetched, probes)
    structure, structure_issues = onpage_more.structure(
        pages,
        kinds,
        home,
        {site_crawl._key(u) for u in menu.top},
        lambda u: site_crawl.classify(u, menu),
    )
    image_extra, image_issues = onpage_more.images_more(pages, probes)
    issues += (
        link_issues
        + onpage_more.host_checks(probes)
        + onpage_more.home_checks(home_html, probes)
        + onpage_more.freshness([(p["_text"], pages[p["url"]]) for p in service])
        + structure_issues
        + onpage_more.locations(pages, kinds)
        + onpage_more.providers(pages)
        + onpage_more.schema_vs_page(home_html, home_text)
        + image_issues
    )
    if access:
        core = [home, *(u for u in urls if site_crawl.classify(u, menu) in CORE)]
        on_page["access"], found = crawl_access.judge(
            access, home, home_html, list(dict.fromkeys(core)), parsed
        )
        issues += [_site_issue(key, detail) for key, detail in found]
    page_issues = [i for p in parsed for i in p["issues"]]
    for p in parsed:
        p.pop("_text")
    on_page["pages"] = parsed
    on_page["duplicates"] = dups
    on_page["site_issues"] = issues
    on_page["trust"] = trust
    on_page["local"] = local
    on_page["orphans"] = orphans[:20]
    on_page["links"].update(link_info)
    on_page["images"].update(image_info | image_extra)
    on_page["link_check"] = link_check
    on_page["structure"] = structure
    on_page["probes"] = _probe_summary(probes)
    on_page["summary"] = _summary(page_issues + issues)
