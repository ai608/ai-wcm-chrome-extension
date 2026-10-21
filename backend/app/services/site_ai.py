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
from app.services.site_audit import SERVICES

PAGE_CHARS = 2500
MAX_PAGES = 30
# What a patient expects a good service page to answer. Fixed list, so results are comparable.
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
You get the text of several pages. Return JSON only, with exactly this shape:
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


def page_text(html: str) -> str:
    doc = LexborHTMLParser(html)
    for tag in doc.css("script, style, noscript, svg"):
        tag.decompose()
    title = doc.css_first("title")
    heads = [h.text(strip=True) for h in doc.css("h1, h2, h3")][:20]
    body = doc.css_first("body")
    text = re.sub(r"\s+", " ", body.text(separator=" ", strip=True) if body else "")
    head = f"TITLE: {title.text(strip=True) if title else ''}\nHEADINGS: {' | '.join(heads)}\n"
    return head + text[:PAGE_CHARS]


async def analyze(http: httpx.AsyncClient, pages: dict[str, str]) -> dict[str, Any]:
    chunks = [
        f"=== PAGE {url}\n{page_text(html)}"
        for url, html in list(pages.items())[:MAX_PAGES]
    ]
    return await llm.chat_json(
        http,
        SYSTEM,
        "\n\n".join(chunks),
        max_tokens=3000,
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
