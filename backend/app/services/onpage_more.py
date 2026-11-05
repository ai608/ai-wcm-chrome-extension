import re
from collections import deque
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

import orjson
from selectolax.lexbor import LexborHTMLParser

from app.services import site_crawl
from app.services.constants import LOCAL_BUSINESS_TYPES

# (core severity, other severity, title, why). A None severity means "do not report".
PAGE_ISSUES: dict[str, tuple[str | None, str | None, str, str]] = {
    "mixed_content": (
        "medium",
        "low",
        "Page loads {n} files over plain http",
        "Browsers warn about or block files that load over http on a secure page.",
    ),
    "title_h1_mismatch": (
        "low",
        None,
        "Title and main heading share no words",
        (
            "The title is what Google shows and the heading is what visitors read. "
            "They should name the same thing."
        ),
    ),
    "title_brand_twice": (
        "low",
        "low",
        "The title repeats the same words",
        "A brand or phrase said twice in a title wastes space and looks spammy in search results.",
    ),
    "claims_no_disclaimer": (
        "medium",
        "low",
        "Results claims with no disclaimer on this page",
        "Before-and-after and results claims need a plain 'results may vary' line.",
    ),
    "noindex_header": (
        "critical",
        "high",
        "The server tells Google not to index this page",
        "An X-Robots-Tag noindex header keeps a page out of search even when the page looks fine.",
    ),
}

SITE_ISSUES: dict[str, tuple[str, str, str]] = {
    "host_split": (
        "high",
        "http, https, www and non-www do not all end at one address",
        "Google may treat each address as a separate site and split the ranking between them.",
    ),
    "http_not_redirected": (
        "high",
        "The http address does not redirect to https",
        "Visitors and Google can reach an insecure copy of every page.",
    ),
    "links_broken": (
        "high",
        "{detail} internal links lead to missing pages",
        "Visitors and Google reach a dead end, and the page loses the strength those links carry.",
    ),
    "links_redirect_chain": (
        "medium",
        "{detail} internal links go through two or more redirects",
        "Each redirect slows the visitor and wastes Google's visit. Link straight to the final address.",
    ),
    "links_redirect": (
        "low",
        "{detail} internal links point to an address that redirects",
        "Link straight to the final address so the visitor and Google need no extra step.",
    ),
    "robots_blocks_bing": (
        "high",
        "robots.txt blocks Bing",
        "Bing's index also feeds ChatGPT search and other tools, so a block hides the site there too.",
    ),
    "robots_blocks_ai": (
        "medium",
        "robots.txt blocks AI crawlers ({detail})",
        (
            "AI assistants such as ChatGPT and Perplexity cannot read the site, so they cannot cite it. "
            "Allow them if you want to appear in AI answers."
        ),
    ),
    "no_favicon": (
        "low",
        "No favicon",
        "The small icon in browser tabs and search results. Without it the site looks unfinished.",
    ),
    "no_social_tags": (
        "low",
        "Links shared on social media have no preview ({detail})",
        "Open Graph and Twitter tags set the picture and title shown when someone shares a page.",
    ),
    "no_updated_date": (
        "low",
        "{detail} service pages show no last-updated date",
        "Google looks for fresh, reviewed information on health pages.",
    ),
    "deep_pages": (
        "low",
        "{detail} service pages are 3 or more clicks from the home page",
        "Pages buried deep get less attention from Google and from visitors.",
    ),
    "service_no_booking_link": (
        "low",
        "{detail} service pages have no booking or contact link in their text",
        "A visitor who is ready should find the next step on the page, not only in the menu.",
    ),
    "service_no_related_links": (
        "low",
        "{detail} service pages link to no other service",
        "Links between related services help visitors and Google see the whole picture.",
    ),
    "locations_incomplete": (
        "medium",
        "{detail} location pages lack their own address, phone or markup",
        "Each location should show its own address and phone, and say so in its markup.",
    ),
    "schema_no_provider": (
        "low",
        "Provider pages have no Physician or Person markup",
        "Markup tells Google who the provider is and what their credentials are.",
    ),
    "schema_phone_mismatch": (
        "medium",
        "The markup says {detail}, a number the page does not show",
        "Markup that does not match the page lowers trust in the business listing.",
    ),
    "schema_address_mismatch": (
        "medium",
        "The markup address ({detail}) is not on the page",
        "Markup that does not match the page lowers trust in the business listing.",
    ),
    "images_no_dimensions": (
        "low",
        "{detail} images have no width and height",
        "Without them the page jumps as pictures load, which annoys visitors and hurts the speed score.",
    ),
    "images_large": (
        "medium",
        "{detail} home page images are over 400 KB",
        "Large pictures slow down the page visitors see first.",
    ),
    "images_css_background": (
        "low",
        "{detail} pictures are set as CSS backgrounds",
        "Google cannot index a background picture and it has no alt text.",
    ),
    "tap_targets_small": (
        "medium",
        "Buttons and links are too small or too close together on phones",
        "Visitors on phones tap the wrong thing and give up.",
    ),
    "viewport_blocks_zoom": (
        "medium",
        "The page stops visitors zooming in",
        "People with poor eyesight need to enlarge text. Blocking zoom also fails accessibility checks.",
    ),
    "field_lcp_poor": (
        "high",
        "Real visitors wait too long for the main content ({detail})",
        "Google measures this on real phones and uses it as a ranking signal.",
    ),
    "field_inp_poor": (
        "high",
        "Real visitors find the page slow to respond to taps ({detail})",
        "Google measures this on real phones and uses it as a ranking signal.",
    ),
    "field_cls_poor": (
        "medium",
        "Real visitors see the page jump while it loads ({detail})",
        "Google measures this on real phones and uses it as a ranking signal.",
    ),
}

LARGE_IMAGE_BYTES = 400_000
BROKEN_STATUS = (404, 410)

_STOP = frozenset(
    (
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "in",
        "for",
        "to",
        "at",
        "on",
        "with",
        "your",
        "our",
        "by",
        "near",
        "best",
        "top",
        "is",
        "are",
        "from",
        "you",
        "we",
        "us",
        "all",
        "any",
        "new",
        "more",
    )
)
_TITLE_SPLIT = re.compile(r"\s+[|\-–—]\s+|\s*[:·•»]\s*")
_CLAIM = re.compile(
    r"before\s*(?:and|&|/|\+)\s*after"
    r"|\bguarantee[ds]?\s+(?:\w+\s+){0,2}(?:results?|success|outcomes?|weight loss|improvement)"
    r"|permanent results"
    r"|\blose\s+\d+\s*(?:lbs?|pounds)\b|\b\d{2,3}\s*%\s*of\s+(?:our\s+)?(?:patients|clients)",
    re.IGNORECASE,
)
_UPDATED = re.compile(
    r"(last\s+)?(updated|reviewed|modified)\s*[:\-]?\s*(on\s+)?"
    r"([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_UPDATED_META = re.compile(
    r"article:modified_time|og:updated_time|itemprop=[\"']dateModified|\"dateModified\"",
    re.IGNORECASE,
)
_BOOKING = re.compile(
    r"\b(?:book|appointment|schedule|consult|contact|reserve|request|get started|call)",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\b\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b")
_ADDRESS = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.\s]{2,40}?\s(?:st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive"
    r"|ln|lane|way|ct|court|pkwy|parkway|hwy|highway|suite|ste)\b",
    re.IGNORECASE,
)
_PROVIDER_URL = re.compile(
    r"/(providers?|doctors?|physicians?|our-team|team|staff|meet-[a-z-]+|dr-[a-z-]+)(/|$)",
    re.IGNORECASE,
)
# Not a picture a visitor sees: hidden, a 1x1 pixel, or an analytics beacon.
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)
_TRACKER = re.compile(r"pixel|beacon|tracker|tracking|analytics", re.IGNORECASE)
_BG_IMAGE = re.compile(r"background(?:-image)?\s*:[^;\"']*url\(", re.IGNORECASE)


def is_picture(img: Any) -> bool:
    src = _attr(img, "src")
    if not src or src.startswith("data:") or _TRACKER.search(src):
        return False
    if "hidden" in img.attributes or _HIDDEN_STYLE.search(_attr(img, "style")):
        return False
    return not (_attr(img, "width") == "1" and _attr(img, "height") == "1")


def issue(key: str, core: bool, url: str | None, **ctx: Any) -> dict[str, Any] | None:
    hi, lo, title, detail = PAGE_ISSUES[key]
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


def site_issue(key: str, detail: str = "") -> dict[str, Any]:
    severity, title, why = SITE_ISSUES[key]
    return {
        "key": key,
        "severity": severity,
        "title": title.format(detail=detail),
        "detail": why,
        "url": None,
    }


def _attr(node: Any, key: str) -> str:
    return (node.attributes.get(key) or "").strip() if node else ""


def _flat(node: Any) -> str:
    return " ".join(node.text(separator=" ", strip=True).split()) if node else ""


def _words(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) > 2 and w not in _STOP
    }


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)[-10:]


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


def _types(item: dict[str, Any]) -> set[str]:
    raw = item.get("@type", [])
    return {str(t).lower() for t in (raw if isinstance(raw, list) else [raw])}


# ── one page ──────────────────────────────────────────────────────────────────────────────


def mixed_count(html: str, url: str) -> int:
    """Files on an https page that load over plain http (links to other pages do not count)."""
    if urlsplit(url).scheme != "https":
        return 0
    doc = LexborHTMLParser(html)
    nodes = doc.css(
        "img[src], script[src], iframe[src], source[src], video[src], audio[src], embed[src]"
    )
    n = sum(1 for x in nodes if _attr(x, "src").lower().startswith("http://"))
    n += sum(
        1
        for x in doc.css('link[rel~="stylesheet"][href]')
        if _attr(x, "href").lower().startswith("http://")
    )
    return n


def brand_twice(title: str) -> bool:
    """The same segment twice ("Glow | Botox | Glow"), or the last segment inside an earlier one."""
    parts = [
        " ".join(re.findall(r"[a-z0-9]+", p.lower())) for p in _TITLE_SPLIT.split(title)
    ]
    parts = [p for p in parts if len(p) >= 3]
    if any(parts.count(p) > 1 for p in parts):
        return True
    return (
        len(parts) >= 2
        and len(parts[-1]) >= 6
        and any(parts[-1] in p for p in parts[:-1])
    )


def page_checks(
    html: str,
    url: str,
    *,
    title: str,
    h1: str,
    text: str,
    core: bool,
    has_disclaimer: bool,
    fetched: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """The extra per-page issues. `fetched` is what the read of this URL revealed (fetchlog)."""
    found: list[dict[str, Any] | None] = []
    n = mixed_count(html, url)
    if n:
        found.append(issue("mixed_content", core, url, n=n))
    if (
        title
        and h1
        and _words(title)
        and _words(h1)
        and not (_words(title) & _words(h1))
    ):
        found.append(issue("title_h1_mismatch", core, url))
    if title and brand_twice(title):
        found.append(issue("title_brand_twice", core, url))
    if core and _CLAIM.search(text) and not has_disclaimer:
        found.append(issue("claims_no_disclaimer", core, url))
    header = str((fetched or {}).get("x_robots") or "").lower()
    if re.search(r"\b(noindex|none)\b", header):
        found.append(issue("noindex_header", core, url))
    return [i for i in found if i]


# ── links, redirects and hosts ────────────────────────────────────────────────────────────


def link_checks(
    fetched: dict[str, dict[str, Any]] | None, probes: dict[str, Any] | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Broken links and redirects, from the pages we read (free) and the links we probed."""
    broken: list[dict[str, Any]] = []
    chains: list[dict[str, Any]] = []
    redirects: list[dict[str, Any]] = []

    def sort(
        url: str, status: Any, hops: int, final: str, found_on: str | None
    ) -> None:
        row = {
            "url": url,
            "status": status,
            "hops": hops,
            "final": final,
            "found_on": found_on,
        }
        if status in BROKEN_STATUS:
            broken.append(row)
        elif isinstance(status, int) and status < 400 and hops >= 2:
            chains.append(row)
        elif isinstance(status, int) and status < 400 and hops == 1:
            redirects.append(row)

    for url, info in (fetched or {}).items():
        sort(
            url,
            info.get("status"),
            int(info.get("hops") or 0),
            str(info.get("final") or url),
            None,
        )
    for p in (probes or {}).get("links", []):
        sort(
            p["url"],
            p.get("status"),
            int(p.get("hops") or 0),
            str(p.get("final") or ""),
            p.get("found_on"),
        )
    seen: set[str] = set()
    issues: list[dict[str, Any]] = []
    for key, rows, floor in (
        ("links_broken", broken, 1),
        ("links_redirect_chain", chains, 1),
        (
            "links_redirect",
            redirects,
            3,
        ),  # a few redirects are normal; many are a pattern
    ):
        fresh = []
        for r in rows:  # a URL is reported once, under the worst problem it has
            if r["url"] not in seen:
                seen.add(r["url"])
                fresh.append(r)
        rows[:] = fresh
        if len(rows) >= floor:
            issues.append(site_issue(key, str(len(rows))))
    info = {
        "checked": len(fetched or {}) + len((probes or {}).get("links", [])),
        "broken": broken[:10],
        "chains": chains[:10],
        "redirects": redirects[:10],
    }
    return info, issues


def host_checks(probes: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Do the four ways to type the address all end in one place, and is http sent to https?"""
    answered = [
        h
        for h in (probes or {}).get("hosts", [])
        if isinstance(h.get("status"), int) and h["status"] < 400
    ]
    if len(answered) < 2:
        return []
    ends = {
        (urlsplit(h["final"]).scheme, (urlsplit(h["final"]).hostname or "").lower())
        for h in answered
    }
    issues: list[dict[str, Any]] = []
    if any(
        h["url"].startswith("http://") and h["final"].startswith("http://")
        for h in answered
    ):
        issues.append(site_issue("http_not_redirected"))
    if len(ends) > 1:
        issues.append(site_issue("host_split"))
    return issues


# ── the home page: icon and sharing tags ──────────────────────────────────────────────────


def home_checks(home_html: str, probes: dict[str, Any] | None) -> list[dict[str, Any]]:
    doc = LexborHTMLParser(home_html)
    issues: list[dict[str, Any]] = []
    icon = (probes or {}).get("favicon")  # only probed when the page has no icon tag
    # No tag and no /favicon.ico (which browsers ask for anyway). Untested (icon is None) is no
    # verdict: a site we could not probe may well have the file.
    has_tag = (
        doc.css_first('link[rel~="icon"], link[rel="apple-touch-icon"]') is not None
    )
    if not has_tag and isinstance(icon, dict) and icon.get("status") != 200:
        issues.append(site_issue("no_favicon"))
    missing = [
        label
        for label, sel in (
            ("og:title", 'meta[property="og:title"]'),
            ("og:image", 'meta[property="og:image"]'),
            ("twitter:card", 'meta[name="twitter:card"]'),
        )
        if not _attr(doc.css_first(sel), "content")
    ]
    if missing:
        issues.append(site_issue("no_social_tags", ", ".join(missing)))
    return issues


# ── freshness, structure, locations, providers ────────────────────────────────────────────


def freshness(pages: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """`pages` is (visible text, html) of each service page."""
    if len(pages) < 2:
        return []
    undated = sum(
        1
        for text, html in pages
        if not (_UPDATED.search(text) or _UPDATED_META.search(html))
    )
    return (
        [site_issue("no_updated_date", f"{undated} of {len(pages)}")]
        if undated * 2 >= len(pages)
        else []
    )


def _internal(html: str, page_url: str, home: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for a in LexborHTMLParser(html).css("a[href]"):
        href = _attr(a, "href")
        if not href or href.startswith(("#", "mailto:", "tel:", "sms:", "javascript:")):
            continue
        url = site_crawl.clean_url(urljoin(page_url, href), home)
        if url:
            out.append((url, _flat(a)))
    return out


def _content_links(html: str, page_url: str, home: str) -> list[tuple[str, str]]:
    """Links in the page's own text, not in its header, menu, footer or sidebar. `tel:` links
    count as booking links."""
    doc = LexborHTMLParser(html)
    for node in doc.css(
        "header, nav, footer, aside, [role=navigation], [role=banner], [role=contentinfo]"
    ):
        node.decompose()
    out: list[tuple[str, str]] = []
    for a in doc.css("a[href]"):
        href = _attr(a, "href")
        if href.startswith(("tel:", "sms:")):
            out.append((href, "call"))
            continue
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        url = site_crawl.clean_url(urljoin(page_url, href), home)
        out.append((url or href, _flat(a)))
    return out


def structure(
    read: dict[str, str],
    kinds: dict[str, str],
    home: str,
    menu_keys: set[str],
    classify: Callable[[str], str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Click depth from the home page, and whether service pages point onward."""
    home_key = site_crawl._key(home)
    graph: dict[str, set[str]] = {home_key: set(menu_keys)}
    for url, html in read.items():
        graph.setdefault(site_crawl._key(url), set()).update(
            site_crawl._key(u) for u, _ in _internal(html, url, home)
        )
    depth = {home_key: 0}
    queue = deque([home_key])
    while queue:
        cur = queue.popleft()
        for nxt in graph.get(cur, ()):
            if nxt not in depth:
                depth[nxt] = depth[cur] + 1
                queue.append(nxt)
    service = [
        u for u, k in kinds.items() if k in ("service", "menu_child", "hub_child")
    ]
    deep = [u for u in service if depth.get(site_crawl._key(u), 0) >= 3]
    no_booking: list[str] = []
    no_related: list[str] = []
    for u in service:
        links = _content_links(read[u], u, home)
        self_key = site_crawl._key(u)
        if not any(
            h.startswith(("tel:", "sms:")) or _BOOKING.search(t) or _BOOKING.search(h)
            for h, t in links
        ):
            no_booking.append(u)
        if not any(
            site_crawl._key(h) != self_key
            and classify(h) in ("service", "menu_child", "hub_child")
            for h, _ in links
            if h.startswith("http")
        ):
            no_related.append(u)
    issues: list[dict[str, Any]] = []
    if deep:
        issues.append(site_issue("deep_pages", str(len(deep))))
    if len(service) >= 2 and no_booking:
        issues.append(site_issue("service_no_booking_link", str(len(no_booking))))
    if len(service) >= 2 and no_related:
        issues.append(site_issue("service_no_related_links", str(len(no_related))))
    info = {
        "deep": deep[:10],
        "no_booking_link": no_booking[:10],
        "no_related_links": no_related[:10],
        "max_depth": max(depth.values(), default=0),
    }
    return info, issues


def locations(read: dict[str, str], kinds: dict[str, str]) -> list[dict[str, Any]]:
    """Several location pages: each one needs its own address, phone and markup."""
    pages = [
        u
        for u in read
        if site_crawl.CITY.search(u)
        and not re.search(r"/(locations?|service-areas?)/?$", u, re.IGNORECASE)
    ]
    if len(pages) < 2:
        return []
    bad = 0
    for u in pages:
        doc = LexborHTMLParser(read[u])
        items = _jsonld(doc)
        for tag in doc.css("script, style, noscript"):
            tag.decompose()
        text = _flat(doc.css_first("body"))
        has_schema = any(_types(i) & LOCAL_BUSINESS_TYPES for i in items)
        if not (_PHONE.search(text) and _ADDRESS.search(text) and has_schema):
            bad += 1
    return [site_issue("locations_incomplete", f"{bad} of {len(pages)}")] if bad else []


def providers(read: dict[str, str]) -> list[dict[str, Any]]:
    pages = [u for u in read if _PROVIDER_URL.search(urlsplit(u).path)]
    if not pages:
        return []
    has = any(
        _types(i) & {"physician", "person"}
        for u in pages
        for i in _jsonld(LexborHTMLParser(read[u]))
    )
    return [] if has else [site_issue("schema_no_provider")]


def schema_vs_page(home_html: str, home_text: str) -> list[dict[str, Any]]:
    """The business markup must say what the page says."""
    issues: list[dict[str, Any]] = []
    local = [
        i
        for i in _jsonld(LexborHTMLParser(home_html))
        if _types(i) & LOCAL_BUSINESS_TYPES
    ]
    marked = {_digits(str(i["telephone"])) for i in local if i.get("telephone")} - {""}
    shown = {_digits(m.group()) for m in _PHONE.finditer(home_text)}
    if marked and shown and not (marked & shown):
        issues.append(site_issue("schema_phone_mismatch", min(marked)))
    for item in local:
        addr = item.get("address")
        street = str(addr.get("streetAddress") or "") if isinstance(addr, dict) else ""
        m = re.match(r"\s*(\d+)\s+([A-Za-z0-9]+)", street)
        if m and not re.search(
            rf"\b{m.group(1)}\b\s+{re.escape(m.group(2))}", home_text, re.IGNORECASE
        ):
            issues.append(site_issue("schema_address_mismatch", street.strip()))
            break
    return issues


# ── images ────────────────────────────────────────────────────────────────────────────────


def images_more(
    read: dict[str, str], probes: dict[str, Any] | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    no_dims = pages_with = backgrounds = bg_pages = 0
    for html in read.values():
        doc = LexborHTMLParser(html)
        lacking = sum(
            1
            for i in doc.css("img[src]")
            if is_picture(i) and not (_attr(i, "width") and _attr(i, "height"))
        )
        no_dims += lacking
        pages_with += 1 if lacking else 0
        bg = sum(1 for n in doc.css("[style]") if _BG_IMAGE.search(_attr(n, "style")))
        backgrounds += bg
        bg_pages += 1 if bg else 0
    large = [
        {"url": i["url"], "bytes": i["length"]}
        for i in (probes or {}).get("images", [])
        if isinstance(i.get("length"), int)
        and i["length"] > LARGE_IMAGE_BYTES
        and isinstance(i.get("status"), int)
        and i["status"] < 400
    ]
    issues: list[dict[str, Any]] = []
    if no_dims >= 3:
        issues.append(
            site_issue("images_no_dimensions", f"{no_dims} (on {pages_with} pages)")
        )
    if large:
        issues.append(site_issue("images_large", str(len(large))))
    if backgrounds:
        issues.append(
            site_issue("images_css_background", f"{backgrounds} (on {bg_pages} pages)")
        )
    info = {
        "no_dimensions": no_dims,
        "css_backgrounds": backgrounds,
        "large": large[:10],
        "sizes_checked": len(
            [i for i in (probes or {}).get("images", []) if i.get("length")]
        ),
    }
    return info, issues


# ── PageSpeed: phones and real visitors ───────────────────────────────────────────────────


def speed_issues(speed: dict[str, Any] | None) -> list[dict[str, Any]]:
    """What the PageSpeed run says beyond the score. `field` is real-visitor data (Chrome's
    CrUX); small sites often have none, and then nothing is reported."""
    if not speed:
        return []
    issues: list[dict[str, Any]] = []
    if speed.get("tap_targets_ok") is False:
        issues.append(site_issue("tap_targets_small"))
    if speed.get("zoom_ok") is False:
        issues.append(site_issue("viewport_blocks_zoom"))
    field = speed.get("field") or {}
    # (issue, key holding Google's FAST/AVERAGE/SLOW verdict, key holding the value)
    for key, verdict, label in (
        ("field_lcp_poor", "lcp", "lcp_ms"),
        ("field_inp_poor", "inp", "inp_ms"),
        ("field_cls_poor", "cls_category", "cls"),
    ):
        value = field.get(label)
        if field.get(verdict) == "SLOW" and isinstance(value, int | float):
            shown = {
                "lcp_ms": f"{value / 1000:.1f} s",
                "inp_ms": f"{int(value)} ms",
            }.get(label, f"{value:.2f}")
            issues.append(site_issue(key, shown))
    return issues
