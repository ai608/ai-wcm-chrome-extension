"""What a clinic website's address says about a page, in one place.

Every pattern here comes from real sites (93 clinic leads, 59 readable): the folder names they
use for locations, services, blogs and team pages, and the pages that merely look like them
(a team page with a city in its name, a promo called /woodinville-vip/, "target-area" meaning
body areas). `tests/test_page_patterns.py` holds the real paths each rule was written from.

Paths are cleaned first (`clean_path`), so `.html`, `%20`, case and slashes never matter.
"""

import re
from urllib.parse import unquote, urlsplit

_EXT = re.compile(r"\.(?:html?|php\d?|aspx?|jsp)$")


def clean_path(url: str) -> str:
    """ "/Cedar%20Park/About-Us.html" -> "/cedar-park/about-us". Home is "". A bare path is fine."""
    path = urlsplit(url if "://" in url or url.startswith("/") else "/" + url).path
    # a decoded %3F or %23 is part of the name, not a query or fragment: cleaning twice must agree
    path = (
        re.sub(r"[?#]", "-", unquote(path)).lower().replace(" ", "-").replace("_", "-")
    )
    prev = None
    while path != prev:  # each step can expose the next: "a.html-" -> "a.html" -> "a"
        prev = path
        path = re.sub(r"/{2,}", "/", path).rstrip("/")
        path = _EXT.sub("", re.sub(r"-+(?=/|$)", "", path))
    return path


def _words(*alts: str) -> str:
    return "|".join(alts)


# ── places ────────────────────────────────────────────────────────────────────────────────
# A folder that holds location pages: /locations/boulder, /location/tx/carrollton,
# /service-areas/st-george-ut, /about/locations/lohi, /areas-served/…, /areas-we-serve.
# Deliberately NOT bare "area": /target-area/face and /area/chest are body areas.
AREA_FOLDER = re.compile(
    r"(?:^|/)(?:"
    + _words(
        r"locations?",
        r"service-?areas?",
        r"areas?-(?:we-)?serve[d]?",
        r"cities",
        r"neighborhoods",
        r"serving",
        r"coverage",
    )
    + r")(?:/|$)"
)
# The index of them even when it is one flat slug: /avere-beauty-locations, /our-location.
AREA_INDEX = re.compile(
    r"(?:^|[/-])(?:locations?|service-?areas?|areas?-(?:we-)?serve[d]?)$"
)
# One office per slug: /biltmore-office, /scottsdale-office.
AREA_OFFICE = re.compile(r"(?:^|/)[a-z0-9]+(?:-[a-z0-9]+)*-(?:office|location)$")
# "Near me" pages that name the place: /dexa-scans-near-me-in-sandy-ut. A bare
# /spider-vein-removal-near-me is a service page with an SEO slug: no place in it.
NEAR_ME = re.compile(r"-near-me-(?:in-)?[a-z]")

# ── page types that carry a city name but are no area page ───────────────────────────────
_END = r"(?=/|$|-)"
_START = r"(?:^|/|-)"


def _kind(*alts: str) -> re.Pattern[str]:
    """The word anywhere in a slug as a whole token: /aesthetician-careers-in-dallas."""
    return re.compile(_START + "(?:" + _words(*alts) + ")" + _END)


def _segment(*alts: str, whole: bool = False) -> re.Pattern[str]:
    """The word at the start of a path segment (or, with `whole`, as the entire segment):
    /test/ is a utility page, /covid-test/ is not."""
    return re.compile(
        r"(?:^|/)(?:" + _words(*alts) + ")" + (r"(?=/|$)" if whole else _END)
    )


# Never counted as a page of the site at all.
UTILITY = _segment(
    r"site-?map",
    r"html-sitemap",
    r"404(?:-error)?",
    r"coming-soon",
    r"maintenance",
    r"test",
    r"sample-(?:page|blog)(?:-\d+)?",
    r"hello-world",
    r"home-?\d+",
    r"home-duplicate",
    r"[a-z0-9-]+-duplicate",
    r"lander",
    r"search",
    r"feed",
    r"wp-(?:content|json|admin|login)",
    r"admin",
    r"auth",
    r"login",
    r"dashboard",
    r"mcp",
    r"api",
    whole=True,
)
SHOP = _segment(
    r"cart",
    r"checkout",
    r"my-account",
    r"shop",
    r"store",
    r"products?",
    r"product-category",
    r"basket",
    r"wishlist",
    r"gift-?cards?",
)
LEGAL = _kind(
    r"privacy(?:-policy)?",
    r"terms(?:-and-conditions|-of-(?:use|service))?",
    r"disclaimer",
    r"hipaa",
    r"hippa",
    r"policies",
    r"policy",
    r"do-not-sell[a-z-]*",
    r"accessibility",
    r"cookie(?:-policy)?",
    r"notice-of-privacy[a-z-]*",
)
FORMS = _kind(
    r"forms?",
    r"consents?",
    r"intake",
    r"new-patients?",
    r"patient-(?:forms|portal|resources)",
    r"downloadable-forms",
    r"pre-post-care",
    r"pre-care",
    r"aftercare",
    r"post-care",
    r"medical-release[a-z-]*",
)
CAREERS = _kind(
    r"careers?",
    r"jobs?",
    r"employment",
    r"hiring",
    r"join-(?:our-)?team",
    r"work-with-us",
)
TEAM = re.compile(
    r"(?:^|/)(?:"
    + _words(
        r"(?:our-|meet-(?:the-|our-)?|the-)?(?:team|staff|providers?|doctors?|physicians?)",
        r"team-members?",
        r"our-medical-team",
        r"medical-team",
        r"meet-[a-z-]+",
        r"dr-[a-z]+(?:-[a-z]+){0,3}",
        r"provider-[a-z-]+",
        r"[a-z-]+-team(?:-[a-z-]+)?",  # /our-dallas-team, /lemmon-team-frisco
    )
    + r")(?:/|$)"
)
# Campaigns and events: /woodinville-vip/, /sip-and-glow-woodinville/, /seattle-sun-insider/.
PROMO = _kind(
    r"vip",
    r"insider",
    r"sip-and-[a-z]+",
    r"giveaway",
    r"promos?",
    r"promotions?",
    r"specials?",
    r"offers?",
    r"events?",
    r"webinars?",
    r"sweepstakes",
    r"first-light",
    r"activated",
    r"confirmation",
    r"thank-you",
    r"referral",
    r"black-friday",
    r"sale",
)
PROOF_PAGE = _kind(
    r"testimonials?",
    r"reviews?",
    r"before-and-after",
    r"before-after",
    r"gallery",
    r"results",
    r"case-stud(?:y|ies)",
    r"success-stories",
)
BOOKING = _kind(
    r"contact(?:-us)?",
    r"book(?:-now|-online|-appointment|ing)?",
    r"schedule",
    r"appointments?",
    r"make-an-appointment",
    r"get-started",
    r"request-[a-z-]+",
    r"consultation",
    r"map",
    r"directions",
)

# ── blogs ─────────────────────────────────────────────────────────────────────────────────
# /blog/x, /news/x, /posts/x, /news-updates/x, /holistic-health-news/x, /articles/x.
BLOG_FOLDER = re.compile(
    r"(?:^|/)(?:blogs?|news|news-updates|posts|articles|[a-z-]+-news|resources)(?:/|$)"
)
BLOG_INDEX_PATH = re.compile(
    r"(?:^|/)(?:blogs?|news|news-updates|posts|articles|[a-z-]+-news|resources)$"
)
DATED = re.compile(r"(?:^|/)\d{4}/\d{1,2}(?:/|$)")
ARCHIVE = re.compile(
    r"(?:^|/)(?:category|tag|author|page|feed|wp-content|wp-json)(?:/|$)"
)

# ── services ──────────────────────────────────────────────────────────────────────────────
SERVICE_FOLDER = re.compile(
    r"(?:^|/)(?:"
    + _words(
        r"services?",
        r"service-page",
        r"treatments?",
        r"procedures?",
        r"med-spa-services",
        r"injectables",
        r"therapies",
        r"offerings",
        r"what-we-do",
        r"solutions",
        r"programs?",
    )
    + r")/"
)
# ── in a service-plus-place slug: "-in-dallas-tx", "-near-layton-ut", "-near-me-in-sandy-utah"
_STATES = (
    r"a[klrz]|c[aot]|d[ce]|fl|ga|hi|i[adln]|k[sy]|la|m[adeinost]|n[cdehjmvy]|o[hkr]|pa|ri|s[cd]"
    r"|t[nx]|ut|v[at]|w[aivy]"
)
_STATE_NAMES = (
    "alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia"
    "|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts"
    "|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new-hampshire|new-jersey"
    "|new-mexico|new-york|north-carolina|north-dakota|ohio|oklahoma|oregon|pennsylvania"
    "|rhode-island|south-carolina|south-dakota|tennessee|texas|utah|vermont|virginia"
    "|washington|west-virginia|wisconsin|wyoming"
)
IN_NEAR = re.compile(
    r"-(?:in|near)-(?:me-in-)?(?P<place>[a-z0-9]+(?:-[a-z0-9]+)*?)"
    rf"(?:-(?:{_STATES}|{_STATE_NAMES}))?(?:-for-(?:men|women))?$"
)


def place_candidates(path: str) -> list[str]:
    """The place a service-plus-place slug names: "/botox-in-dallas-tx" -> ["dallas"]."""
    m = IN_NEAR.search(clean_path(path))
    return [m.group("place")] if m else []


# ── what a path is ────────────────────────────────────────────────────────────────────────


def is_area_path(url: str) -> bool:
    """A page that is, by its address, a location or service-area page (or their index)."""
    return kind(url) == "area"


def kind(url: str) -> str:
    """The first of these that fits: utility, shop, legal, forms, careers, team, archive, blog,
    promo, proof, booking, area, service_place, service, other. Cheap rules on the address only.
    "service_place" is a candidate (/aging-in-place-care fits it): nothing here knows real places."""
    p = clean_path(url)
    if not p:
        return "home"
    if AREA_FOLDER.search(p):
        return "area"  # a location folder beats every word that happens to sit under it
    for name, rx in (
        ("utility", UTILITY),
        ("shop", SHOP),
        ("legal", LEGAL),
        ("forms", FORMS),
        ("careers", CAREERS),
        ("team", TEAM),
    ):
        if rx.search(p):
            return name
    if ARCHIVE.search(p):
        return "archive"
    if BLOG_INDEX_PATH.search(p):
        return "blog_index"
    if BLOG_FOLDER.search(p) or DATED.search(p):
        return "blog_post"
    for name, rx in (("promo", PROMO), ("proof", PROOF_PAGE), ("booking", BOOKING)):
        if rx.search(p):
            return name
    if AREA_INDEX.search(p) or AREA_OFFICE.search(p) or NEAR_ME.search(p):
        return "area"
    if IN_NEAR.search(p):
        return "service_place"  # /botox-in-dallas-tx: a service slug that names a place
    if SERVICE_FOLDER.search(p + "/"):
        return "service"
    return "other"


def in_area_folder(url: str) -> bool:
    """Inside a location folder (/areas-served/…, /about/locations/…), whatever the slug says."""
    return bool(AREA_FOLDER.search(clean_path(url)))


def in_blog(url: str) -> bool:
    """Under a blog-like folder (or it is that folder): /blog/x, /news-updates/x, /holistic-health-news."""
    return bool(BLOG_FOLDER.search(clean_path(url)))


def is_blog_index(url: str) -> bool:
    """The blog's own listing page: /blog, /blogs/, /news-updates/."""
    return bool(BLOG_INDEX_PATH.search(clean_path(url)))


def is_archive(url: str, service_terms: tuple[str, ...] = ()) -> bool:
    """A category, tag, author, paging, feed or uploads address: not a page of the site. But some
    sites keep their services under /category/ (vivaskinlounge.com/category/botox): a top-level
    category named for a service is a service."""
    p = clean_path(url)
    if not ARCHIVE.search(p):
        return False
    if p.startswith("/category/"):
        tail = p.removeprefix("/category/").replace("-", " ")
        return not any(t in tail for t in service_terms)
    return True
