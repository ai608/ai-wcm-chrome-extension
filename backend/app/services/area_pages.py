"""The pages a clinic has for the areas it says it serves, and whether they are any good.

Per claimed area: `covered` (a page of its own, no problems), `needs_work` (a page of its own
with problems), `mentioned` (no page of its own, but other pages name the area) or `missing`.
A page of its own is one whose address names the area, or whose title and H1 both do.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser

from app.services import page_patterns

THIN_WORDS = 300  # a city page shorter than this has said little about the city
SHINGLE = 5  # words per fingerprint piece
MIN_SHINGLES = 20  # shorter pages are never called copies
DUPLICATE_AT = (
    0.8  # share of identical pieces, city names ignored, that makes two pages copies
)


def fold(text: str) -> str:
    """Lower case without accents, so "San José" meets /san-jose/. Letters of other scripts stay."""
    plain = unicodedata.normalize("NFKD", text)
    return "".join(c for c in plain if not unicodedata.combining(c)).lower()


def norm(url: str) -> str:
    """One key for every spelling of an address: /tampa, /tampa/ and www.x.com/tampa/."""
    p = urlsplit(url)
    return p.netloc.lower().removeprefix("www.") + p.path.rstrip("/").lower()


def match_name(area: str) -> str:
    """The place itself: "Austin, TX", "Austin, Texas" and "Austin (TX)" are all "Austin"."""
    return re.sub(r"\(.*?\)", "", area.split(",")[0]).strip()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(match_name(name))).strip("-")


# Pages that carry a place name without being a page for that place: /our-dallas-team,
# /woodinville-vip, /azani-testimonials-lehigh-valley, /blog/best-spa-austin, /cart/. (The home
# page is not in the list: a one-city clinic's home page is its page for that city.)
_NOT_AREA_PAGE = frozenset(
    {
        "utility",
        "shop",
        "legal",
        "forms",
        "careers",
        "team",
        "archive",
        "blog_index",
        "blog_post",
        "promo",
        "proof",
        "booking",
    }
)


def pages_named(area: str, urls: list[str]) -> list[str]:
    """Pages whose address names the area as a whole word: /tampa/, /iv-therapy-tampa/,
    /weight-loss/florida/st-petersburg/ for "St. Petersburg", /…-colorado-springs.html. Team,
    careers, promo, proof, booking, blog and shop pages are not area pages."""
    slug = _slug(area)
    if not slug:
        return []
    word = re.compile(rf"(?:^|[/-]){re.escape(slug)}(?:$|[/-])")
    # ponytail: a keyword match on the address, not a read of the page. A page that merely
    # has the city in its slug counts; read the page text if that ever proves too generous.
    return [
        u
        for u in urls
        if page_patterns.kind(u) not in _NOT_AREA_PAGE
        and word.search(page_patterns.clean_path(u))
    ]


@dataclass
class Read:
    title: str = ""
    h1s: list[str] = field(default_factory=list)
    text: str = ""  # everything on the page: where an area is "mentioned"
    body: str = (
        ""  # without menu, header, footer and sidebars: what the page itself says
    )
    noindex: bool = False

    @property
    def words(self) -> int:
        return len(re.findall(r"\w+", self.body))


def read(html: str) -> Read:
    doc = LexborHTMLParser(html)
    for junk in doc.css("script, style, noscript"):
        junk.decompose()
    title = doc.css_first("title")
    robots = " ".join(
        (m.attributes.get("content") or "").lower()
        for m in doc.css("meta")
        if (m.attributes.get("name") or "").lower() in ("robots", "googlebot")
    )
    # Title and H1 first: a hero H1 often sits inside <header>, which is cut away below.
    out = Read(
        title=fold((title.text() if title else "").strip()),
        h1s=[fold(h.text().strip()) for h in doc.css("h1")],
        noindex="noindex" in robots,
    )
    out.text = fold(doc.body.text(separator=" ")) if doc.body else ""
    for chrome in doc.css("nav, header, footer, aside"):
        chrome.decompose()
    out.body = fold(doc.body.text(separator=" ")) if doc.body else ""
    if not re.search(r"\w", out.body):
        out.body = (
            out.text
        )  # a layout that puts the whole page inside <header>: not "empty"
    return out


def _term(area: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(fold(match_name(area)))}(?!\w)")


def _shingles(text: str, terms: re.Pattern[str]) -> set[str]:
    words = re.findall(r"\w+", terms.sub(" areaname ", text))
    return {" ".join(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


def _similarity(a: set[str], b: set[str]) -> float:
    if len(a) < MIN_SHINGLES or len(b) < MIN_SHINGLES:
        return 0.0
    return len(a & b) / len(a | b)


def _unique(areas: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for a in areas:
        name = a.strip()
        if match_name(
            name
        ):  # "(Texas)" or "," name no place: matched against pages it would hit all
            seen.setdefault(fold(name), name)
    return list(seen.values())


def grade(
    areas: list[str], known: list[str], pages: dict[str, str]
) -> list[dict[str, Any]]:
    """One entry per area: name, status, its own pages, problems (and the area it copies)."""
    areas = _unique(areas)
    # One address per page, however the map or the crawl spelled it; the crawled spelling wins.
    canon = {norm(u): u for u in known}
    canon.update({norm(u): u for u in pages})
    reads = {norm(u): read(h) for u, h in pages.items()}
    patterns = {a: _term(a) for a in areas}
    longest_first = sorted(patterns.items(), key=lambda kv: -len(kv[0]))
    everything = re.compile("|".join(p.pattern for _, p in longest_first) or "(?!)")
    out: list[dict[str, Any]] = []
    best: dict[str, str] = {}
    for area in areas:
        rx = patterns[area]
        own = list(
            dict.fromkeys(norm(u) for u in pages_named(area, list(canon.values())))
        )
        own += [
            n
            for n, r in reads.items()
            if n not in own
            and page_patterns.kind(canon[n]) not in _NOT_AREA_PAGE
            and rx.search(r.title)
            and any(rx.search(h) for h in r.h1s)
        ]
        crawled = [n for n in own if n in reads]
        entry: dict[str, Any] = {
            "name": area,
            "status": "missing",
            "pages": [canon[n] for n in own[:5]],
            "issues": [],
            "duplicate_of": None,
        }
        if crawled:
            # Judge the page that names the area in its title or H1 (/florida/ for "Florida"),
            # not just the longest page whose address has the word in it.
            named = [
                n
                for n in crawled
                if rx.search(reads[n].title) or any(rx.search(h) for h in reads[n].h1s)
            ]
            page = max(named or crawled, key=lambda n: reads[n].words)
            best[area] = page
            r = reads[page]
            if r.noindex:
                entry["issues"].append("noindex")
            if r.words < THIN_WORDS:
                entry["issues"].append("thin")
            if not named:
                entry["issues"].append("title_h1")
        if own:
            entry["status"] = "needs_work" if entry["issues"] else "covered"
        elif any(rx.search(r.text) for r in reads.values()):
            entry["status"] = "mentioned"
        out.append(entry)
    prints = {a: _shingles(reads[n].body, everything) for a, n in best.items()}
    by_name = {e["name"]: e for e in out}
    for i, a in enumerate(list(prints)):
        for b in list(prints)[i + 1 :]:
            if best[a] == best[b]:
                continue  # one page for both cities is not a copy of itself
            if _similarity(prints[a], prints[b]) >= DUPLICATE_AT:
                for x, y in ((a, b), (b, a)):
                    if "duplicate" not in by_name[x]["issues"]:
                        by_name[x]["issues"].append("duplicate")
                        by_name[x]["duplicate_of"] = y
                        by_name[x]["status"] = "needs_work"
    return out
