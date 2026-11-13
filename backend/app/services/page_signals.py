"""What a page says about itself, read from its title, H1, meta tags and structured data.

The address of a page (page_patterns) is a guess; these are statements the page makes. Used by
the Site tab to leave out pages that are not finished, to tell a blog post or a person's page
from a service page, and to find trust pages by what they are called, not where they live.
"""

import re
from urllib.parse import urlsplit

import orjson
from selectolax.lexbor import LexborHTMLParser

from app.services import page_patterns

# Default text that site builders and themes ship with. Verified against each vendor's own
# demo or source (Wix demo sites, WordPress core upgrade.php, Webflow's default div block).
PLACEHOLDER_PHRASES = (
    "lorem ipsum",
    "i'm a paragraph. click here to add your own text",
    "i'm a great place for you to tell a story",
    "i'm a product description",
    "this is an example page",
    "hi, this is a comment",
    "this is some text inside of a div block",
    "welcome to wordpress. this is your first post",
    "heading text here",
    "sample title",
)
# The whole title or H1 is a builder default: "I'm a product", "Hello world!", "Sample Page".
PLACEHOLDER_TITLES = frozenset(
    {"i'm a product", "i'm a title", "hello world!", "sample page", "sample title"}
)
_SOFT_404 = re.compile(
    r"\b(page not found|not found|404|page (?:can't|cannot|could not) be found"
    r"|page (?:doesn't|does not) exist|nothing (?:was )?found)\b"
)
_CREDENTIAL = re.compile(
    r"(?:^|\W)(?:dr\.?\s|md\b|m\.d\.|do\b|np\b|fnp|dnp|pa-c|rn\b|facog|crna)",
    re.IGNORECASE,
)
_TEAM_HEADING = re.compile(
    r"\b(the team|our team|meet (?:the|our) (?:team|providers?|doctors?|staff)|our providers"
    r"|our staff|our doctors)\b"
)

# Trust pages by what the page calls itself (title or H1), lower case.
TRUST_TITLES = {
    "about_page": re.compile(r"^\s*about\b"),
    "team_page": re.compile(
        r"\b(our team|meet (?:the|our) (?:team|providers|doctors|staff)|our providers"
        r"|providers|our staff|our doctors|crew|who is taking care of you)\b"
    ),
    "faq_page": re.compile(r"\b(faqs?|frequently asked|common questions)\b"),
    "pricing_page": re.compile(r"\b(pricing|prices|price list)\b"),
    "financing_page": re.compile(r"\b(financing|payment plans?|payment options)\b"),
    "privacy_policy": re.compile(r"\bprivacy policy\b"),
}
# Trust pages by the words of their address: every word of one set must be in the path.
TRUST_WORDS = {
    "about_page": [],  # matched by the start of the address instead: /about, /about-us
    "team_page": [
        {"team"},
        {"providers"},
        {"provider"},
        {"staff"},
        {"crew"},
        {"our", "doctors"},
    ],
    "faq_page": [
        {"faq"},
        {"faqs"},
        {"frequently", "questions"},
        {"common", "questions"},
    ],
    "pricing_page": [{"pricing"}, {"prices"}, {"price", "list"}],
    "financing_page": [{"financing"}, {"payment", "plans"}, {"payment", "options"}],
    "privacy_policy": [{"privacy"}],
}
_ABOUT = re.compile(r"(?:^|/)about(?:-[a-z]+)?/?$")
_NOT_TRUST_KINDS = frozenset({"shop", "careers", "utility", "blog_post", "archive"})
# Folders that hold lists of posts, never a trust page: /category/mim-providers.
_LISTING = re.compile(r"(?:^|/)(category|categories|tag|tags|author|page)(?:/|$)")


def _norm(text: str) -> str:
    return " ".join(text.replace("’", "'").replace("‘", "'").split()).lower()


def heads(html: str) -> tuple[str, str]:
    """(title, first H1), normalised."""
    doc = LexborHTMLParser(html)
    title = doc.css_first("title")
    h1 = doc.css_first("h1")
    return (
        _norm(title.text(strip=True)) if title else "",
        _norm(h1.text(separator=" ", strip=True)) if h1 else "",
    )


def _title_core(title: str) -> str:
    """ "Botox | Glow Med Spa" -> "botox": the page's own part of a title."""
    return re.split(r"\s+[|–—-]\s+|:\s", title)[0].strip()


def _ld_types(html: str) -> set[str]:
    out: set[str] = set()
    for node in LexborHTMLParser(html).css('script[type="application/ld+json"]')[:20]:
        try:
            data = orjson.loads(node.text())
        except orjson.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            for i in item.get("@graph") or [item]:
                if isinstance(i, dict):
                    t = i.get("@type", [])
                    out |= {str(x).lower() for x in (t if isinstance(t, list) else [t])}
    return out


def _meta(html: str, prop: str) -> str:
    node = LexborHTMLParser(html).css_first(f'meta[property="{prop}"]')
    return (node.attributes.get("content") or "").strip().lower() if node else ""


_TOWN_IN_TITLE = re.compile(
    r"\b([A-Z][a-zA-Z.']+(?: [A-Z][a-zA-Z.']+){0,2}),\s*([A-Z]{2})\b"
)


def title_town(pages: dict[str, str]) -> str | None:
    """The clinic's town when most page titles carry it ("Botox | Plano, TX | Metamorph"):
    a site-wide title suffix, not a topic. None when no "Town, ST" is on enough titles."""
    counts: dict[str, int] = {}
    for html in pages.values():
        node = LexborHTMLParser(html).css_first("title")
        title = node.text(strip=True) if node else ""
        for town in {m.group(1) for m in _TOWN_IN_TITLE.finditer(title)}:
            counts[town] = counts.get(town, 0) + 1
    if not counts:
        return None
    town, n = max(counts.items(), key=lambda kv: kv[1])
    return town if n >= max(TITLE_TOWN_MIN, TITLE_TOWN_SHARE * len(pages)) else None


TITLE_TOWN_MIN = 3
TITLE_TOWN_SHARE = 0.4


def path_words(url: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", urlsplit(url).path.lower()))


# A test page by its address: /test, /test-page, /test-location, /about-us-test. Not a page
# about a medical test (/bioidentical-hormones-test-in-utah, /…-male-performance-test).
_TEST_PAGE = re.compile(
    r"(?:^|/)(?:test\d*|test-(?:page|location|site|post|\d+)"
    r"|(?:about(?:-us)?|home|contact|page|location|services?)-test)$"
)


def unfinished(url: str, html: str | None) -> str | None:
    """Why a page should not be live, or None: builder demo content, a test or copy page, or a
    page that says it was not found while answering 200. Read pages are checked by content;
    pages not read only by address."""
    path = urlsplit(url).path.lower()
    words = path_words(url)
    if "i-m-a-product" in path:
        return "Builder demo product (“I'm a product”)"
    if (
        _TEST_PAGE.search(path.rstrip("/"))
        or re.search(r"(?:^|/)copy-of-", path)
        or "not-being-used" in path
    ):
        return "Test, copy or unused page"
    if "untitled" in words:
        return "Untitled page"
    # WordPress and theme demo content: "Hello world!", "Sample Page", /sample-post-2.
    if re.search(r"(?:^|/)(?:hello-world|sample-page|sample-post(?:-\d+)?)/?$", path):
        return "Theme demo content (sample post or page)"
    if html is None:
        return None
    title, h1 = heads(html)
    if _title_core(title) in PLACEHOLDER_TITLES or h1 in PLACEHOLDER_TITLES:
        return "Builder placeholder title"
    if title.startswith("index of /"):
        return "Server lists the folder's files (directory listing is on)"
    if _SOFT_404.search(_title_core(title)) or _SOFT_404.search(h1):
        return "Says “page not found” but loads"
    return None


# Classes that builders and CSS frameworks use to hide an element (Webflow, Tailwind,
# Bootstrap, WordPress): text inside them is not on the page a visitor sees.
HIDING_CLASSES = frozenset(
    {
        "hidden",
        "hide",
        "is-hidden",
        "w-condition-invisible",
        "d-none",
        "sr-only",
        "visually-hidden",
        "screen-reader-text",
        "invisible",
    }
)
# Elementor hides a section per device; hidden on all three, nobody sees it. Hidden on one
# only, it still shows on the others. (elementor-invisible is only a fade-in's start state.)
_HIDDEN_ON_EVERY_DEVICE = frozenset(
    {"elementor-hidden-desktop", "elementor-hidden-tablet", "elementor-hidden-mobile"}
)
_HIDING_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _page_hiding_classes(doc: LexborHTMLParser) -> set[str]:
    """Single classes the page's own <style> rules hide (.promo-old { display: none })."""
    hidden: set[str] = set()
    for style in doc.css("style"):
        for selectors, body in _CSS_RULE.findall(style.text()):
            if not _HIDING_STYLE.search(body):
                continue
            for sel in selectors.split(","):
                m = re.fullmatch(r"\s*\.([A-Za-z0-9_-]+)\s*", sel)
                if m:
                    hidden.add(m.group(1).lower())
    return hidden


def visible_text(html: str) -> str:
    """The body text a visitor can see: elements hidden by their markup (the hidden attribute,
    aria-hidden, an inline display:none, a hiding class from a builder or from the page's own
    styles) are left out, with everything inside them. A script or animation that hides
    something after the page loads cannot be seen here."""
    doc = LexborHTMLParser(html)
    hiding = HIDING_CLASSES | _page_hiding_classes(doc)
    for node in doc.css("script, style, noscript, template"):
        node.decompose()
    for node in doc.css("body *"):
        if node.parent is None:  # already removed with a hidden ancestor
            continue
        a = node.attributes
        classes = {c.lower() for c in (a.get("class") or "").split()}
        if (
            "hidden" in a
            or (a.get("aria-hidden") or "").lower() == "true"
            or _HIDING_STYLE.search(a.get("style") or "")
            or classes & hiding
            or _HIDDEN_ON_EVERY_DEVICE <= classes
        ):
            node.decompose()
    body = doc.body
    return _norm(body.text(separator=" ")) if body else ""


def placeholder_text(html: str) -> str | None:
    """Builder default text a visitor can see on a page that is otherwise real (a Webflow
    "Title Goes Here" card, a Wix paragraph): worth fixing, but the page still counts. Text
    in hidden elements is not counted: it is not on the page anyone sees."""
    text = visible_text(html)
    hit = next((p for p in PLACEHOLDER_PHRASES if p in text), None)
    return f"Leftover placeholder text (“{hit}”)" if hit else None


# Measured on 136 labeled service pages of 22 clinic sites: og:type=article (72 of them),
# article:published_time (23) and Article structured data are on service pages too, because
# SEO plugins tag every page so. BlogPosting and an author byline never were.
_BYLINE = re.compile(
    r'rel="author"|class="[^"]*\b(byline|post-author|entry-meta|post-meta|posted-on)\b',
    re.IGNORECASE,
)


def is_post(html: str) -> bool:
    """A blog post, by the two signs that never showed on a service page: BlogPosting or
    NewsArticle structured data, or an author byline."""
    return bool(_ld_types(html) & {"blogposting", "newsarticle"}) or bool(
        _BYLINE.search(html)
    )


def is_person(html: str) -> bool:
    """One person's page (a provider's bio), or a team page: og:type profile, a title that
    starts with a credential ("Dr. …", "…, MD") or a team H1."""
    # Person structured data is not used: it is the author markup on many service pages.
    if _meta(html, "og:type") == "profile":
        return True
    title, h1 = heads(html)
    core = _title_core(title)
    return bool(
        _TEAM_HEADING.search(h1)
        or core.startswith(("dr. ", "dr "))
        or re.search(r",\s*(md|do|np|fnp|dnp|pa-c|rn|facog)\b", core)
    )


def trust_pages(urls: list[str], pages: dict[str, str]) -> dict[str, str]:
    """Each trust page found, by key. A page that calls itself one (title or H1) wins over an
    address that only contains the word. Lists of posts (/category/…), shop, careers and
    utility pages never count (/shop/p/a-team-duo-kit, "Join our team")."""
    found: dict[str, str] = {}
    usable = [
        u
        for u in urls
        if urlsplit(u).path.strip("/")  # the home page is never the about or FAQ page
        and not _LISTING.search(urlsplit(u).path.lower())
        and page_patterns.kind(u) not in _NOT_TRUST_KINDS
    ]
    named = {u: heads(pages[u]) for u in usable if u in pages}
    for key, rx in TRUST_TITLES.items():
        # The title first, across every page: an H1 like "About Services" is weaker.
        hit = next(
            (u for u, (t, _) in named.items() if rx.search(_title_core(t))), None
        )
        hit = hit or next((u for u, (_, h1) in named.items() if rx.search(h1)), None)
        if hit:
            found[key] = hit
    by_address = usable
    for key, sets in TRUST_WORDS.items():
        if key in found:
            continue
        if key == "about_page":  # "about" anywhere is too loose: /lets-talk-about-skin
            hit = next(
                (u for u in by_address if _ABOUT.search(urlsplit(u).path.lower())), None
            )
        else:
            hit = next(
                (u for u in by_address if any(s <= path_words(u) for s in sets)), None
            )
        if hit:
            found[key] = hit
    return found
