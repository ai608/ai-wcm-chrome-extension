import html as html_lib
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser

from app.core.exceptions import AppError
from app.services import site_audit

SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")
MAX_FETCHES = 8
MAX_URLS = 5000
MAX_CHILDREN = 5
CHECKED_URLS = 500
LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.DOTALL)


def parse_robots(
    text: str,
) -> tuple[list[tuple[list[str], list[tuple[bool, str]]]], list[str]]:
    """Rule groups [(agents, [(allow, path pattern)])] and the Sitemap lines of a robots.txt."""
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    sitemaps: list[str] = []
    after_agent = False
    for raw in text.splitlines():
        key, _, value = raw.split("#", 1)[0].partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if not after_agent:
                groups.append(([], []))
            groups[-1][0].append(value.lower())
        elif key == "sitemap" and value:
            sitemaps.append(value)
        elif key in ("allow", "disallow") and groups and value:
            groups[-1][1].append((key == "allow", value))
        after_agent = key == "user-agent"
    return groups, sitemaps


def rules_for(groups: list[Any], agent: str) -> list[tuple[bool, str]]:
    """The rules that apply to `agent`: its own group, else the `*` group."""
    for name in (agent, "*"):
        rules = [r for agents, rs in groups if name in agents for r in rs]
        if rules:
            return rules
    return []


def blocked(rules: list[tuple[bool, str]], target: str) -> bool:
    """Google's rule: the longest matching pattern wins, and Allow wins a tie."""
    hits = [
        (len(pattern), allow)
        for allow, pattern in rules
        if re.match(re.escape(pattern).replace(r"\*", ".*").replace(r"\$", "$"), target)
    ]
    return bool(hits) and not max(hits)[1]


def norm(url: str) -> str:
    """A URL without scheme, `www.`, fragment and trailing slash, for comparing."""
    p = urlsplit(url)
    host = (p.hostname or "").lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}{'?' + p.query if p.query else ''}".lower()


def _target(url: str) -> str:
    p = urlsplit(url)
    return (p.path or "/") + (f"?{p.query}" if p.query else "")


def _same_site(a: str, b: str) -> bool:
    return norm(a).split("/")[0] == norm(b).split("/")[0]


async def _get(url: str, accept: tuple[str, ...]) -> tuple[str, str]:
    try:
        return "ok", (await site_audit.fetch_html(url, accept=accept))[0]
    except site_audit.TransientFetchError:
        return "error", ""
    except AppError:
        return "missing", ""


async def load(home: str) -> dict[str, Any]:
    """Read robots.txt and the site's sitemaps. `judge` decides what is wrong."""
    parts = urlsplit(home)
    origin = f"{parts.scheme}://{parts.netloc}"
    state, text = await _get(f"{origin}/robots.txt", ("text/plain",))
    groups, listed = parse_robots(text)
    queue = [u for u in listed if _same_site(u, home)]
    declared = bool(queue)
    queue = queue or [origin + p for p in SITEMAP_PATHS]
    guesses = set() if declared else set(queue)
    files: list[dict[str, Any]] = []
    urls: list[str] = []
    while queue and len(files) < MAX_FETCHES:
        url = queue.pop(0)
        file_state, xml = await _get(url, ("application/xml", "text/xml"))
        locs = [html_lib.unescape(m) for m in LOC.findall(xml)]
        if file_state == "ok" and "<sitemapindex" in xml:
            queue += [u for u in locs[:MAX_CHILDREN] if _same_site(u, home)]
        elif file_state == "ok" and "<urlset" in xml:
            urls += locs
        elif file_state == "ok":
            file_state = "invalid"
        files.append({"url": url, "state": file_state, "urls": len(locs)})
        if file_state == "ok" and url in guesses:
            queue = [q for q in queue if q not in guesses]
    return {
        "state": state,
        "groups": groups,
        "declared": declared,
        "files": files,
        "urls": urls[:MAX_URLS],
        "truncated": len(urls) > MAX_URLS,
    }


def _assets(html: str, base: str) -> list[str]:
    doc = LexborHTMLParser(html)
    found = [
        urljoin(base, n.attributes.get("href") or "")
        for n in doc.css('link[rel="stylesheet"]')
    ] + [urljoin(base, n.attributes.get("src") or "") for n in doc.css("script[src]")]
    return [u for u in dict.fromkeys(found) if _same_site(u, base)]


def judge(
    raw: dict[str, Any],
    home: str,
    home_html: str,
    core: list[str],
    parsed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """What robots.txt and the sitemaps say about the core pages, and the problems found."""
    found: list[tuple[str, str]] = []
    rules = rules_for(raw["groups"], "googlebot")
    if raw["state"] == "error":
        found.append(("robots_unreachable", ""))
    site_blocked = blocked(rules, "/")
    hit_pages = [u for u in core if blocked(rules, _target(u))]
    hit_assets = [u for u in _assets(home_html, home) if blocked(rules, _target(u))]
    if site_blocked:
        found.append(("robots_blocks_site", ""))
    elif hit_pages:
        found.append(("robots_blocks_pages", str(len(hit_pages))))
    if hit_assets:
        found.append(("robots_blocks_assets", str(len(hit_assets))))
    listed = {norm(u) for u in raw["urls"]}
    gap: list[str] = []
    bad: list[str] = []
    sitemap_blocked = [
        u for u in raw["urls"][:CHECKED_URLS] if blocked(rules, _target(u))
    ]
    if not listed:
        found.append(("sitemap_broken" if raw["declared"] else "sitemap_missing", ""))
    else:
        if not raw["declared"]:
            found.append(("sitemap_not_in_robots", ""))
        gap = [u for u in core if norm(u) not in listed] if not raw["truncated"] else []
        bad = [
            p["url"]
            for p in parsed
            if norm(p["url"]) in listed
            and (
                p["noindex"] or p["canonical"]["status"] in ("other_page", "other_host")
            )
        ]
        if gap:
            found.append(("sitemap_missing_pages", str(len(gap))))
        if bad:
            found.append(("sitemap_bad_urls", str(len(bad))))
        if sitemap_blocked:
            found.append(("sitemap_blocked", str(len(sitemap_blocked))))
    info = {
        "robots": {
            "state": raw["state"],
            "blocks_site": site_blocked,
            "blocked_pages": hit_pages[:10],
            "blocked_assets": len(hit_assets),
        },
        "sitemap": {
            "declared": raw["declared"],
            "files": raw["files"],
            "urls": len(raw["urls"]),
            "missing_pages": gap[:10],
            "bad_urls": bad[:10],
            "blocked": len(sitemap_blocked),
        },
    }
    return info, found
