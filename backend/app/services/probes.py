import asyncio
import re
from collections import Counter
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from selectolax.lexbor import LexborHTMLParser

from app.core.exceptions import AppError
from app.services import onpage_more, site_audit, site_crawl

BUDGET_S = 20.0
CONCURRENCY = 3
LINKS = 20
IMAGES = 8
MAX_HOPS = 5
TIMEOUT_S = 8.0
UA = "WCM-Audit/1.0"
REDIRECTS = (301, 302, 303, 307, 308)
# Answers that say the page really is gone. 403/429/5xx can be a firewall or a busy server.
GONE = (404, 410)
# A HEAD answer that may be the server's fault, not the page's: ask again with GET.
RECHECK_WITH_GET = (403, 404, 405, 501)
IMAGE_EXT = re.compile(r"\.(jpe?g|png|gif|webp|avif|svg|ico)(\?|$)", re.IGNORECASE)


async def _once(
    client: httpx.AsyncClient, method: str, url: str
) -> tuple[int, httpx.Headers]:
    """One request with no redirect followed and no body read."""
    current, host = site_audit.normalize_url(url)
    parts = urlsplit(current)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    ip = await site_audit._public_ip(host, port)
    address = f"[{ip}]" if ":" in ip else ip
    target = urlunsplit(
        (parts.scheme, f"{address}:{port}", parts.path, parts.query, "")
    )
    async with client.stream(
        method,
        target,
        headers={"Host": parts.netloc, "User-Agent": UA, "Accept": "*/*"},
        extensions={"sni_hostname": host},
        timeout=httpx.Timeout(TIMEOUT_S),
    ) as response:
        return response.status_code, response.headers


async def head(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Follow redirects by hand (at most MAX_HOPS) and report where the URL ends up.

    {"status", "final", "hops"} plus "x_robots", "length", "type" when the final answer had them.
    "status" is None when the request failed or looped: unknown, not broken."""
    current, hops = url, 0
    try:
        while True:
            status, headers = await _once(client, "HEAD", current)
            if status in RECHECK_WITH_GET:
                status, headers = await _once(client, "GET", current)
            location = headers.get("location")
            if status in REDIRECTS and location:
                hops += 1
                if hops > MAX_HOPS:
                    return {"status": None, "final": current, "hops": hops}
                current = urljoin(current, location)
                continue
            length = headers.get("content-length", "")
            return {
                "status": status,
                "final": current,
                "hops": hops,
                "x_robots": headers.get("x-robots-tag"),
                "length": int(length) if length.isdigit() else None,
                "type": headers.get("content-type"),
            }
    except (AppError, httpx.HTTPError):
        return {"status": None, "final": current, "hops": hops}


def _host_variants(home: str) -> list[str]:
    bare = (urlsplit(home).hostname or "").lower().removeprefix("www.")
    return [
        f"{scheme}://{www}{bare}/"
        for scheme in ("http", "https")
        for www in ("", "www.")
    ]


def link_candidates(
    pages: dict[str, str], home: str, limit: int = LINKS
) -> list[tuple[str, str]]:
    """Internal links found on the read pages that were not read themselves: (url, a page that
    links to it), the most linked first. Menu links repeat on every page, so they rank first."""
    read = {site_crawl._key(u) for u in pages}
    seen: Counter[str] = Counter()
    first: dict[str, tuple[str, str]] = {}
    for page_url, html in pages.items():
        for a in LexborHTMLParser(html).css("a[href]"):
            href = (a.attributes.get("href") or "").strip()
            if not href or href.startswith(
                ("#", "mailto:", "tel:", "sms:", "javascript:")
            ):
                continue
            url = site_crawl.clean_url(urljoin(page_url, href), home)
            if url is None or IMAGE_EXT.search(url):
                continue
            key = site_crawl._key(url)
            if key in read:
                continue
            seen[key] += 1
            first.setdefault(key, (url, page_url))
    return [first[k] for k, _ in seen.most_common(limit)]


def _home_images(html: str, home: str, limit: int = IMAGES) -> list[str]:
    out: list[str] = []
    for img in LexborHTMLParser(html).css("img[src]"):
        src = (img.attributes.get("src") or "").strip()
        if src and onpage_more.is_picture(img):  # not a hidden tracking pixel
            url = urljoin(home, src)
            if url.startswith("http") and url not in out:
                out.append(url)
    return out[:limit]


def has_icon_tag(html: str) -> bool:
    return (
        LexborHTMLParser(html).css_first(
            'link[rel~="icon"], link[rel="apple-touch-icon"]'
        )
        is not None
    )


async def run(*, home: str, home_html: str, pages: dict[str, str]) -> dict[str, Any]:
    """All probes, a few at a time. Whatever has not finished when the budget ends is dropped."""
    sem = asyncio.Semaphore(CONCURRENCY)
    out: dict[str, Any] = {"hosts": [], "links": [], "images": [], "favicon": None}

    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:

        async def probe(url: str) -> dict[str, Any]:
            async with sem:
                return await head(client, url)

        async def host(url: str) -> None:
            out["hosts"].append({"url": url, **await probe(url)})

        async def link(url: str, found_on: str) -> None:
            out["links"].append({"url": url, "found_on": found_on, **await probe(url)})

        async def image(url: str) -> None:
            out["images"].append({"url": url, **await probe(url)})

        async def favicon() -> None:
            icon = urljoin(home, "/favicon.ico")
            out["favicon"] = {"url": icon, **await probe(icon)}

        jobs = [host(u) for u in _host_variants(home)]
        jobs += [link(u, src) for u, src in link_candidates(pages, home)]
        jobs += [image(u) for u in _home_images(home_html, home)]
        if not has_icon_tag(home_html):
            jobs.append(favicon())
        tasks = [asyncio.create_task(j) for j in jobs]
        _, pending = await asyncio.wait(tasks, timeout=BUDGET_S)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    out["timed_out"] = len(pending)
    out["checked"] = len(tasks) - len(pending)
    return out
