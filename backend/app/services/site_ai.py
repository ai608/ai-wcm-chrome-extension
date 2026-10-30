"""AI reading of crawled clinic pages: service topics, providers, areas served, offers.

Keyword checks in site_audit/site_crawl find *whether* pages exist. This pass reads what
the pages *say*. One OpenRouter call per audit; on any error the keyword results stand.
"""

import json
import re
from typing import Any

import httpx
from selectolax.lexbor import LexborHTMLParser

from app.core.config import settings
from app.services import llm
from app.services.constants import SERVICES

# What a patient expects a good service page to answer. Fixed list, so results are comparable.
CHROME_CHARS = 3000  # the site header or footer, sent once
MIN_PAGE_CHARS = 1500  # a page cut shorter than this by the total budget is left out
TOPICS = [
    "What it is",
    "Who it is for",
    "How it works",
    "Results / before and after",
    "Side effects and recovery",
    "Pricing or financing",
    "FAQs",
    "Provider credentials",
    "Booking call to action",
]

SYSTEM = f"""You audit a wellness or med spa clinic website for a marketing agency.
You get the site's header and footer once, then the text of several pages. Return JSON only, with exactly this shape:
{{"services": [{{"service": "<one of: {", ".join(SERVICES)}>",
   "page_url": "<url of the page that covers it>",
   "topics_present": ["<from the topic list>"], "topics_missing": ["<from the topic list>"]}}],
 "providers": [{{"name": "...", "credentials": "<e.g. MD, NP, RN, or empty>", "page_url": "..."}}],
 "areas_served": ["<city or area the site says it serves>"],
 "offers": ["<current special or promotion, short>"],
 "financing": true|false, "insurance_accepted": true|false}}
Topic list: {json.dumps(TOPICS)}.
Rules: only report what the page text shows. Every topic goes in present or missing for
each service. Use only service names from the list. Never invent providers or cities.
Empty lists are fine."""


def _parse(html: str) -> LexborHTMLParser:
    doc = LexborHTMLParser(html)
    for tag in doc.css("script, style, noscript, svg"):
        tag.decompose()
    return doc


def _chrome(doc: LexborHTMLParser) -> list[Any]:
    """The site-wide header and footer. A <header> inside an article, main or section is that
    block's own title, and a header/footer nested in another one goes with its parent: both stay."""

    def site_wide(node: Any) -> bool:
        parent = node.parent
        while parent is not None:
            if parent.tag in ("article", "main", "section", "header", "footer"):
                return False
            parent = parent.parent
        return True

    return [n for n in doc.css("header, footer") if site_wide(n)]


def _flat(node: Any) -> str:
    return (
        re.sub(r"\s+", " ", node.text(separator=" ", strip=True)).strip()
        if node
        else ""
    )


def page_text(html: str) -> str:
    """Title, headings and the whole body text of one page, without the site-wide header and
    footer: they repeat on every page, so site_text() sends them once. Headings are read
    first, as some themes put the H1 inside the header. The text is not cut here; analyze()
    keeps the total inside AI_TOTAL_CHARS."""
    doc = _parse(html)
    title = doc.css_first("title")
    heads = [_flat(h) for h in doc.css("h1, h2, h3")][:20]
    for node in _chrome(doc):
        node.decompose()
    head = f"TITLE: {_flat(title)}\nHEADINGS: {' | '.join(heads)}\n"
    return head + _flat(doc.css_first("body"))


def site_text(html: str) -> str:
    """The home page's header and footer (phone, address, menu, socials), sent once."""
    return "\n".join(
        f"{node.tag.upper()}: {_flat(node)[:CHROME_CHARS]}"
        for node in _chrome(_parse(html))
        if _flat(node)
    )


async def analyze(http: httpx.AsyncClient, pages: dict[str, str]) -> dict[str, Any]:
    """One AI call over the site header/footer and the pages in reading order (home first,
    then services, then the rest). Pages are sent whole until AI_TOTAL_CHARS runs out; the
    page that does not fit is cut, and later pages (the least important) are left out."""
    chunks: list[str] = []
    left = settings.AI_TOTAL_CHARS
    items = list(pages.items())[: settings.AI_MAX_PAGES]
    # pages starts with the home page (see research._enrich)
    if items and (chrome := site_text(items[0][1])):
        chunks.append(f"=== SITE HEADER AND FOOTER (same on every page)\n{chrome}")
        left -= len(chrome)
    for url, html in items:
        text = page_text(html)
        if left < MIN_PAGE_CHARS:
            break
        chunks.append(f"=== PAGE {url}\n{text[:left]}")
        left -= len(text)
    return await llm.chat_json(
        http,
        SYSTEM,
        "\n\n".join(chunks),
        max_tokens=6000,
        model=settings.RESEARCH_MODEL,
    )


def _strings(value: Any, limit: int = 20) -> list[str]:
    return (
        [str(v).strip()[:120] for v in value if str(v).strip()][:limit]
        if isinstance(value, list)
        else []
    )


def apply(sections: dict[str, Any], ai: dict[str, Any], pages: dict[str, str]) -> None:
    """Merge the AI result into `site`. Anything malformed is dropped, never trusted."""
    site = sections["site"]
    clusters = {c["service"]: c for c in site["services"]["clusters"]}
    for item in ai.get("services") or []:
        if not isinstance(item, dict) or item.get("service") not in SERVICES:
            continue
        present = [t for t in _strings(item.get("topics_present")) if t in TOPICS]
        missing = [t for t in TOPICS if t not in present]
        cluster = clusters.get(item["service"])
        if cluster is None:  # the AI found a service the URLs didn't show
            url = str(item.get("page_url") or "")
            cluster = {
                "service": item["service"],
                "found": 1,
                "expected": 3,
                "pages": [url] if url in pages else [],
                "topics_present": [],
                "topics_missing": [],
            }
            site["services"]["clusters"].append(cluster)
            clusters[item["service"]] = cluster
        cluster["topics_present"] = sorted(
            set(cluster["topics_present"]) | set(present), key=TOPICS.index
        )
        cluster["topics_missing"] = [
            t for t in missing if t not in cluster["topics_present"]
        ]
    site["services"]["cluster_pages_found"] = sum(
        c["found"] for c in site["services"]["clusters"]
    )
    site["services"]["cluster_pages_expected"] = sum(
        c["expected"] for c in site["services"]["clusters"]
    )

    city_text = " ".join(site["cities"]["city_pages"]).lower().replace("-", " ")
    areas = _strings(ai.get("areas_served"))
    site["cities"]["claimed_not_built"] = [
        a for a in areas if a.lower() not in city_text
    ][:20]

    providers = [
        p for p in ai.get("providers") or [] if isinstance(p, dict) and p.get("name")
    ]
    credentialed = [p for p in providers if str(p.get("credentials") or "").strip()]
    offers = _strings(ai.get("offers"), 5)
    extras = [
        (
            "provider_credentials",
            "Provider credentials shown",
            bool(credentialed),
            next(
                (str(p.get("page_url")) for p in credentialed if p.get("page_url")),
                None,
            ),
        ),
        (
            "insurance_info",
            "Insurance information",
            ai.get("insurance_accepted") is True,
            None,
        ),
    ]
    trust = [t for t in site["trust"] if t["key"] not in {k for k, *_ in extras}]
    site["trust"] = trust + [
        {"key": k, "label": label, "status": "found" if ok else "missing", "url": url}
        for k, label, ok, url in extras
    ]
    convert = sections["convert"]
    convert["offers_or_specials"] = convert["offers_or_specials"] or bool(offers)
    convert["financing_mentioned"] = (
        convert["financing_mentioned"] or ai.get("financing") is True
    )
    site[
        "ai"
    ] = {  # extra context for the panel/report; unknown keys are ignored by the UI
        "providers": [
            {
                "name": str(p["name"])[:80],
                "credentials": str(p.get("credentials") or "")[:40],
            }
            for p in providers
        ][:20],
        "areas_served": areas,
        "offers": offers,
        "model": settings.RESEARCH_MODEL,
    }
