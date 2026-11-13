"""Save a clinic site's real crawl as a golden fixture, so the Site logic can be scored offline.

Run from backend/:  .venv/bin/python -m tests.golden.capture viva=https://vivaskinlounge.com/ ...

It reads the home page and crawls the site exactly like an audit (Firecrawl is used when the
key is set and the site needs it), then keeps only what the Site logic reads: the home HTML,
every URL found and the HTML of every page read. Styles, scripts (except JSON-LD) and comments
are removed and the file is gzipped, so a site is a few hundred KB, not megabytes.
Expected answers live next to it in <name>.expected.json and are written by a person.
"""

import asyncio
import gzip
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx

from app.services import audit_runner, site_crawl

HERE = Path(__file__).parent
_DROP = re.compile(
    r"<style\b.*?</style>|<!--.*?-->|<svg\b.*?</svg>"
    r"|<script\b(?![^>]*application/ld\+json)[^>]*>.*?</script>"
    r"|data:[a-z/+.-]+;base64,[A-Za-z0-9+/=]+"  # inline images: never read
    r'|\s[\w:-]+="[^"]{2000,}"',  # pasted blobs (design-tool clipboard data)
    re.IGNORECASE | re.DOTALL,
)


def slim(html: str) -> str:
    return _DROP.sub("", html)


class _Trace:
    async def report(self, *_a: Any, **_k: Any) -> None:
        return None


async def capture(http: httpx.AsyncClient, name: str, url: str) -> None:
    _, final_url, home_html, via, _ = await audit_runner._home(http, url, {}, _Trace())
    menu = site_crawl.nav_links(home_html, final_url)
    urls, pages, _, _ = await site_crawl.crawl(
        http, final_url, home_html, via, None, menu
    )
    data = {
        "name": name,
        "url": url,
        "final_url": final_url,
        "via": via,
        "home_html": slim(home_html),
        "urls": urls,
        "pages": {u: slim(h) for u, h in pages.items()},
    }
    out = HERE / f"{name}.json.gz"
    out.write_bytes(gzip.compress(json.dumps(data).encode()))
    print(
        f"{name}: {len(urls)} urls, {len(pages)} pages read, via {via}, "
        f"{out.stat().st_size // 1024} KB"
    )


async def main(pairs: list[str]) -> None:
    async with httpx.AsyncClient(timeout=10) as http:
        sem = asyncio.Semaphore(3)

        async def one(pair: str) -> None:
            name, url = pair.split("=", 1)
            async with sem:
                try:
                    await capture(http, name, url)
                except Exception as exc:  # noqa: BLE001  one bad site must not stop the rest
                    print(f"{name}: FAILED {type(exc).__name__}: {exc}")

        await asyncio.gather(*(one(p) for p in pairs))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
