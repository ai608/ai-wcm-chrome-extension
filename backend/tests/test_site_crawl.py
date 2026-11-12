import asyncio
import copy
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.exceptions import AppError
from app.services import site_audit, site_crawl

HOME = "https://glow.example/"
URLS = [
    HOME,
    "https://glow.example/services/botox",
    "https://glow.example/services/botox-for-men",
    "https://glow.example/semaglutide-weight-loss",
    "https://glow.example/locations/",
    "https://glow.example/locations/austin",
    "https://glow.example/blog/",
    "https://glow.example/blog/what-is-tirzepatide",
    "https://glow.example/before-and-after",
    "https://glow.example/about-us",
    "https://glow.example/faq",
    "https://glow.example/reviews",
]
POST = '<html><head><meta property="article:published_time" content="2026-09-01T10:00:00Z"></head><body><a href="/services/botox">Botox</a></body></html>'
BOOK = (
    '<html><body><script src="https://www.vagaro.com/widget.js"></script></body></html>'
)


def base_sections():
    return site_audit.analyze(
        "<html><head><title>Glow</title></head><body><h1>Glow</h1></body></html>", HOME
    )


G = "https://glow.example"
RICH = (
    "<html><body><p>" + "Botox results last three months. " * 30 + "</p></body></html>"
)
THIN = "<html><body><div id='app'></div></body></html>"
MENU = f"""<html><body><header><nav><ul>
<li><a href="{G}/">Home</a></li>
<li><a href="{G}/internal-optimization/">Internal Optimization</a><ul>
  <li><a href="{G}/peptide-therapy/">Peptide Therapy</a></li>
  <li><a href="{G}/iv-therapy/">IV Therapy</a></li></ul></li>
<li><span></span><a href="{G}/about/">About</a><ul>
  <li><a href="{G}/our-story/">Our story</a></li></ul></li>
<li><a href="{G}/contact/">Contact</a></li>
</ul></nav></header><main><a href="{G}/before-and-after/">Results</a></main></body></html>"""


def test_clean_url_merges_variants_and_drops_files_and_other_hosts():
    home = f"{G}/"
    assert (
        site_crawl.clean_url("http://www.glow.example/botox?utm=x#top", home)
        == f"{G}/botox"
    )
    assert site_crawl.clean_url("https://other.example/botox", home) is None
    assert site_crawl.clean_url(f"{G}/menu.pdf", home) is None
    assert site_crawl.clean_url(f"{G}/wp-json/v2/posts", home) is None
    assert site_crawl.clean_url("mailto:a@glow.example", home) is None
    assert site_crawl.clean_url(f"{G}/locations.kml", home) is None


def test_nav_links_reads_dropdowns_whatever_their_label():
    menu = site_crawl.nav_links(MENU, f"{G}/")
    assert menu.children == {
        f"{G}/peptide-therapy/": "Internal Optimization",
        f"{G}/iv-therapy/": "Internal Optimization",
        f"{G}/our-story/": "About",
    }
    assert menu.parents == {
        f"{G}/internal-optimization/": "Internal Optimization",
        f"{G}/about/": "About",
    }
    assert len(menu.top) == 7 and f"{G}/contact/" in menu.top
    assert site_crawl.classify(f"{G}/internal-optimization/", menu) == "hub"
    # not in SERVICES, found by the menu
    assert site_crawl.classify(f"{G}/peptide-therapy/", menu) == "menu_child"
    assert site_crawl.classify(f"{G}/iv-therapy/", menu) == "service"
    # an About dropdown holds no services
    assert site_crawl.classify(f"{G}/our-story/", menu) == "other"
    # static sites keep the .html ending
    assert site_crawl.classify(f"{G}/services.html", menu) == "hub"


def test_nav_links_ignores_a_dropdown_heading_linked_to_hash():
    html = f"""<nav><ul><li><a href="#">Resources</a><ul>
      <li><a href="{G}/blog/">Blog</a></li></ul></li></ul></nav>"""
    assert site_crawl.nav_links(html, f"{G}/").parents == {}


def test_tiers_put_one_page_per_service_first_then_round_robin():
    urls = [
        f"{G}{p}"
        for p in (
            "/",
            "/botox/faq",
            "/botox",
            "/botox-lip-flip",
            "/weight-loss",
            "/weight-loss/semaglutide-program",
            "/treatments",
            "/treatments/morpheus8",
            "/sculptra",
            "/about-us",
            "/meet-our-team",
            "/pricing",
            "/blog",
            "/blog/post-1",
            "/locations",
            "/locations/austin",
            "/contact",
            "/tag/botox/",
        )
    ]
    menu = site_crawl.Menu(
        {f"{G}/sculptra": "Treatments"},
        {},
        {f"{G}/sculptra": "", f"{G}/botox": "", f"{G}/weight-loss": ""},
    )
    t = site_crawl.tiers(urls, f"{G}/", menu)
    assert t["A"] == [f"{G}/treatments", f"{G}/botox", f"{G}/weight-loss"]
    assert t["B"] == [f"{G}/sculptra", f"{G}/treatments/morpheus8"]  # menu first
    assert t["C"] == [
        f"{G}{p}"
        for p in ("/meet-our-team", "/pricing", "/about-us", "/locations", "/blog")
    ]
    assert t["D"] == [
        f"{G}{p}"
        for p in ("/botox-lip-flip", "/weight-loss/semaglutide-program", "/botox/faq")
    ]
    # no home, posts or tag archives
    assert t["E"] == [f"{G}/locations/austin", f"{G}/contact"]
    chosen, groups, mode = site_crawl.plan(urls, f"{G}/", menu)
    assert mode == "all" and chosen == [u for b in t.values() for u in b]
    assert [g["name"] for g in groups] == list(site_crawl.TIER_NAMES.values())


def test_tiers_keep_blog_posts_and_keyword_only_urls_out_of_services():
    # Astra: posts sit at the root and carry service words in their slugs
    urls = [
        f"{G}/low-testosterone/",
        f"{G}/what-to-expect-with-first-botox-appointment",
        f"{G}/bhrt-vs-traditional-hrt",
    ]
    menu = site_crawl.Menu({}, {}, {f"{G}/low-testosterone/": "low t"})
    posts = {site_crawl._key(f"{G}/bhrt-vs-traditional-hrt")}
    t = site_crawl.tiers(urls, f"{G}/", menu, posts)
    assert t["A"] == [f"{G}/low-testosterone/"]  # a menu page is the main page
    # a URL that only contains "botox" is no main page; the post is no service at all
    assert t["D"] == [f"{G}/what-to-expect-with-first-botox-appointment"]
    assert f"{G}/bhrt-vs-traditional-hrt" not in [u for b in t.values() for u in b]


def test_every_menu_page_is_read_before_any_page_the_menu_does_not_list():
    # Astra: three hormone pages are in the menu, and only one can be the "main" page
    urls = [
        f"{G}{p}"
        for p in ("/low-testosterone/", "/bhrt/", "/hormone-programs/", "/hrt-tips")
    ]
    menu = site_crawl.Menu(
        {},
        {},
        {
            f"{G}/low-testosterone/": "low t",
            f"{G}/bhrt/": "bhrt",
            f"{G}/hormone-programs/": "programs",
        },
    )
    t = site_crawl.tiers(urls, f"{G}/", menu)
    assert t["A"] == [f"{G}/bhrt/"]  # fewest path segments, shortest URL
    assert t["B"] == [f"{G}/low-testosterone/", f"{G}/hormone-programs/"]  # menu order
    assert t["D"] == [f"{G}/hrt-tips"]  # only a page the menu does not list


def test_trust_pages_are_found_by_their_menu_text_when_the_url_does_not_say():
    html = f"""<nav><ul><li><a href="{G}/integrative-health-programs-cost.html">Cost</a></li>
    <li><a href="{G}/integrative-health-specialist.html">About Mary Ann</a></li>
    <li><a href="{G}/recipes.html">Recipes</a></li></ul></nav>"""
    menu = site_crawl.nav_links(html, f"{G}/")
    cost, about, recipes = (
        f"{G}/integrative-health-programs-cost.html",
        f"{G}/integrative-health-specialist.html",
        f"{G}/recipes.html",
    )
    assert (
        site_crawl.classify(cost, menu) == "trust"
        and site_crawl.classify(recipes, menu) == "other"
    )
    t = site_crawl.tiers([cost, about, recipes], f"{G}/", menu)
    assert t["C"] == [cost, about]  # CONTEXT order: pricing before about
    sections = base_sections()
    site_crawl.enrich(sections, [cost, about, recipes], {}, None, menu)
    trust = {x["key"]: x["url"] for x in sections["site"]["trust"]}
    assert trust["pricing_page"] == cost and trust["about_page"] == about


def test_plan_caps_a_big_site_and_passes_unused_slots_down():
    urls = [f"{G}/treatments"] + [f"{G}/treatments/t{i:02}" for i in range(60)]
    chosen, groups, mode = site_crawl.plan(urls, f"{G}/")
    by = {g["name"]: g for g in groups}
    assert mode == "tiers" and len(chosen) <= site_crawl.settings.CRAWL_MAX_PAGES
    # A used 1 of its 20 slots, so B gets its own 12 plus the 19 left over
    assert len(by["Other treatments"]["picked"]) == 31
    assert by["Other treatments"]["skipped"] == 29
    assert chosen[0] == f"{G}/treatments"


@pytest.mark.anyio
async def test_reader_falls_back_to_firecrawl_within_its_cap(monkeypatch):
    monkeypatch.setattr(site_crawl.settings, "FIRECRAWL_API_KEY", "fake")
    monkeypatch.setattr(site_crawl.settings, "FIRECRAWL_FALLBACKS", 1)
    direct = {f"{G}/thin": THIN, f"{G}/rich": RICH}

    async def fetch(url, **_kw):
        if url not in direct:
            raise AppError(422, "site_unreachable", "blocked")
        return direct[url], url

    async def scrape(_http, url):
        return RICH

    monkeypatch.setattr(site_crawl, "fetch_html", fetch)
    monkeypatch.setattr(site_crawl, "scrape", scrape)
    read = site_crawl._Reader(None, f"{G}/", direct=True)
    assert await read(f"{G}/rich") == (RICH, "direct")
    # thin page: likely JavaScript
    assert await read(f"{G}/thin") == (RICH, "firecrawl")
    assert await read(f"{G}/blocked") == (None, "direct")  # the one fallback is used up
    assert await site_crawl._Reader(None, f"{G}/", direct=False)(f"{G}/x") == (
        RICH,
        "firecrawl",
    )


# The page SiteGround serves to a crawler it distrusts: HTTP 200, no title, no text, only a redirect.
WALL = (
    '<html><head><link rel="icon" href="data:;">'
    '<meta http-equiv="refresh" content="0;/.well-known/sgcaptcha/?r=%2Fservices%2F"></head></html>'
)
CLOUDFLARE = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"
SHORT_REAL = (
    "<html><head><title>Hormone Assessment | Renew</title></head>"
    "<body><h1>Hormone Assessments</h1></body></html>"
)
LONG_WITH_CAPTCHA = (
    "<html><head><title>Contact</title></head><body><p>"
    + "Call us to book a visit today. " * 30
    + "Please complete the captcha below.</p></body></html>"
)


@pytest.mark.parametrize(
    ("html", "blocked"),
    [
        (WALL, True),
        ("<html></html>", True),
        (CLOUDFLARE, True),
        (SHORT_REAL, False),  # short but real: audited as a thin page, never dropped
        (LONG_WITH_CAPTCHA, False),  # a real page may mention a captcha
        (RICH, False),
    ],
)
def test_blocked_matches_bot_walls_and_empty_replies_but_not_short_real_pages(
    html, blocked
):
    assert site_crawl._blocked(html) is blocked


@pytest.mark.anyio
async def test_reader_never_returns_a_bot_wall_as_the_page(monkeypatch):
    pages = {f"{G}/wall": WALL, f"{G}/short": SHORT_REAL}

    async def fetch(url, **_kw):
        return pages[url], url

    monkeypatch.setattr(site_crawl, "fetch_html", fetch)
    read = site_crawl._Reader(
        None, f"{G}/", direct=True
    )  # no Firecrawl key: no fallback
    assert await read(f"{G}/wall") == (None, "blocked")
    assert await read(f"{G}/short") == (SHORT_REAL, "direct")


@pytest.mark.anyio
async def test_firecrawl_result_that_is_a_bot_wall_is_dropped_too(monkeypatch):
    monkeypatch.setattr(site_crawl.settings, "FIRECRAWL_API_KEY", "fake")

    async def fetch(url, **_kw):
        return WALL, url

    async def scrape(_http, _url):
        return CLOUDFLARE

    monkeypatch.setattr(site_crawl, "fetch_html", fetch)
    monkeypatch.setattr(site_crawl, "scrape", scrape)
    read = site_crawl._Reader(None, f"{G}/", direct=True)
    assert await read(f"{G}/x") == (None, "firecrawl")


@pytest.mark.anyio
async def test_crawl_reports_a_blocked_page_as_failed_and_never_audits_it(monkeypatch):
    async def fetch(url, **_kw):
        return (WALL if "iv-therapy" in url else RICH), url

    monkeypatch.setattr(site_crawl, "fetch_html", fetch)
    events, report = recorder()
    _, pages, _, _ = await site_crawl.crawl(None, f"{G}/", MENU, "direct", report)
    wall = f"{G}/iv-therapy/"
    assert wall not in pages and f"{G}/peptide-therapy/" in pages
    status, detail = events[f"page:{wall}"]
    assert status == "failed" and detail["via"] == "blocked"
    assert events["scrape"][1]["failed"] == 1


def recorder():
    events: dict[str, tuple[str, dict]] = {}

    async def report(step, status, **detail):
        events[step] = (status, detail)

    return events, report


@pytest.mark.anyio
async def test_crawl_without_key_uses_the_menu_and_keeps_pages_finished_in_time(
    monkeypatch,
):
    monkeypatch.setattr(site_crawl.settings, "CRAWL_BUDGET_S", 0.2)

    async def fetch(url, **_kw):
        if "our-story" in url:
            await asyncio.sleep(5)
        return RICH, url

    monkeypatch.setattr(site_crawl, "fetch_html", fetch)
    events, report = recorder()
    _, pages, ok, _ = await site_crawl.crawl(None, f"{G}/", MENU, "direct", report)
    assert ok and events["map"][1]["sources"] == {"map": 0, "menu": 7, "home": 8}
    assert list(pages)[:2] == [f"{G}/internal-optimization/", f"{G}/iv-therapy/"]
    assert f"{G}/peptide-therapy/" in pages and f"{G}/our-story/" not in pages
    scrape = events["scrape"][1]
    assert scrape["timed_out"] == 1 and scrape["direct"] == len(pages)


POSTS_XML = f"""<urlset><url><loc>{G}/bhrt-guide</loc>
<lastmod>2026-09-01</lastmod></url></urlset>"""


@pytest.mark.anyio
async def test_crawl_reads_the_menu_first_and_adds_map_pages_only_at_the_end(
    monkeypatch,
):
    monkeypatch.setattr(site_crawl.settings, "FIRECRAWL_API_KEY", "fake")
    order: list[str] = []

    async def fetch(url, **_kw):
        if url.endswith("post-sitemap.xml"):
            return POSTS_XML, url
        if url.endswith(".xml"):
            raise AppError(422, "site_unreachable", "none")
        order.append(url)
        return RICH, url

    async def slow_map(_http, _url):
        await asyncio.sleep(0.05)
        order.append("map done")
        return [f"{G}/treatments", f"{G}/botox-aftercare-tips", f"{G}/bhrt-guide"]

    monkeypatch.setattr(site_crawl, "fetch_html", fetch)
    monkeypatch.setattr(site_crawl, "map_site", slow_map)
    events, report = recorder()
    urls, pages, ok, sitemap = await site_crawl.crawl(
        None, f"{G}/", MENU, "direct", report
    )
    assert ok and order.index(f"{G}/internal-optimization/") < order.index("map done")
    # map pages go to "More service pages" / "Other pages" only: a hub found by map
    # does not jump the queue, and the post from the sitemap is never read
    assert f"{G}/botox-aftercare-tips" in pages and f"{G}/treatments" not in pages
    assert f"{G}/bhrt-guide" in urls and f"{G}/bhrt-guide" not in pages
    assert [p["url"] for p in sitemap] == [f"{G}/bhrt-guide"]
    assert events["map"][1]["sources"]["map"] == 3


@pytest.mark.anyio
async def test_a_slow_map_is_dropped_and_a_broken_map_marks_the_crawl(monkeypatch):
    monkeypatch.setattr(site_crawl.settings, "FIRECRAWL_API_KEY", "fake")
    monkeypatch.setattr(site_crawl.settings, "CRAWL_MAP_TIMEOUT_S", 0.05)

    async def fetch(url, **_kw):
        return RICH, url

    async def slow(_http, _url):
        await asyncio.sleep(5)
        return []

    async def broken(_http, _url):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(site_crawl, "fetch_html", fetch)
    monkeypatch.setattr(site_crawl, "map_site", slow)
    events, report = recorder()
    _, pages, ok, _ = await site_crawl.crawl(None, f"{G}/", MENU, "direct", report)
    assert ok and events["map"][0] == "failed"  # slow: dropped, not a provider error
    assert events["map"][1]["error"] == "Timed out" and f"{G}/peptide-therapy/" in pages

    monkeypatch.setattr(site_crawl, "map_site", broken)
    events, report = recorder()
    _, pages, ok, _ = await site_crawl.crawl(None, f"{G}/", MENU, "direct", report)
    assert not ok and events["map"][1]["error"] == "ConnectError"
    assert f"{G}/peptide-therapy/" in pages


def test_enrich_uses_whole_site():
    sections = base_sections()
    site_crawl.enrich(
        sections,
        URLS,
        {
            "https://glow.example/blog/what-is-tirzepatide": POST,
            "https://glow.example/faq": BOOK,
        },
    )
    site = sections["site"]
    names = {c["service"] for c in site["services"]["clusters"]}
    assert {"Neurotoxins", "Medical Weight Loss"} <= names
    botox = next(
        c for c in site["services"]["clusters"] if c["service"] == "Neurotoxins"
    )
    assert botox["found"] == 2 and botox["expected"] >= botox["found"]
    assert site["cities"]["pages_found"] == 2 and site["cities"]["hub_page"] is True
    assert site["blog"]["post_count"] == 1
    assert site["blog"]["last_post_at"].startswith("2026-09-01")
    assert site["blog"]["links_to_services"] is True
    assert site["proof"]["before_after_gallery"] and site["proof"]["reviews_page"]
    trust = {t["key"]: t["status"] for t in site["trust"]}
    assert trust["about_page"] == "found" and trust["pricing_page"] == "missing"
    assert site["pages_crawled"] == 3
    assert sections["convert"]["booking_platform"] == "Vagaro"
    assert (
        next(c for c in sections["convert"]["checks"] if c["key"] == "online_booking")[
            "status"
        ]
        == "ok"
    )


def test_enrich_without_pages_keeps_home_data_shape():
    sections = base_sections()
    before = copy.deepcopy(sections["convert"])
    site_crawl.enrich(sections, [], {})
    assert sections["convert"]["booking_platform"] == before["booking_platform"]
    assert sections["site"]["pages_crawled"] == 1


# WordPress default: posts live at /<slug>/, outside /blog/ (e.g. 305euphoria.com).
BLOG_INDEX_HTML = """<html><body>
<article><h2 class="entry-title"><a href="https://glow.example/best-skin-tightening/">Best Skin Tightening</a></h2>
  <a href="https://glow.example/category/skin/">Skin</a>
  <div class="meta"><a href="https://glow.example/author/glow/">Glow</a>
  <time datetime="2026-08-28T12:52:43+00:00">August 28, 2026</time></div></article>
<article><h2><a href="/laser-hair-removal-cost/">How Much Is Laser Hair Removal?</a></h2>
  <time datetime="2026-01-08T05:59:57+00:00">January 8, 2026</time></article>
<footer><time datetime="2020-01-01">Copyright</time></footer>
</body></html>"""

POST_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?><urlset>
<url><loc>https://glow.example/best-skin-tightening/</loc><lastmod>2026-09-02T00:00:00+00:00</lastmod></url>
<url><loc>https://glow.example/old-post/</loc><lastmod>2024-03-17T17:18:01+00:00</lastmod></url>
<url><loc>https://glow.example/category/skin/</loc></url>
</urlset>"""


def test_index_posts_reads_post_cards_outside_blog_path():
    posts = site_crawl.index_posts(BLOG_INDEX_HTML, "https://glow.example/blog/")
    assert [p["url"] for p in posts] == [
        "https://glow.example/best-skin-tightening/",
        "https://glow.example/laser-hair-removal-cost/",
    ]
    assert posts[0]["title"] == "Best Skin Tightening"
    assert posts[0]["published_at"].startswith("2026-08-28")


@pytest.mark.anyio
async def test_blog_posts_uses_index_then_sitemap(monkeypatch):
    calls = []

    async def fake_fetch(url, accept=("text/html",)):
        calls.append(url)
        if url.endswith("/post-sitemap.xml"):
            return POST_SITEMAP, url
        raise AppError(422, "site_unreachable", "missing")

    monkeypatch.setattr(site_crawl, "fetch_html", fake_fetch)
    posts = await site_crawl.blog_posts(
        None,
        [HOME, "https://glow.example/blog/"],
        {"https://glow.example/blog/": BLOG_INDEX_HTML},
        HOME,
    )
    # the sitemap's lastmod is not a publish date, so the undated old post's page is read
    assert calls == [
        "https://glow.example/post-sitemap.xml",
        "https://glow.example/old-post/",
    ]
    # index entries come first, so their titles and dates win over the sitemap's
    assert posts[0]["title"] == "Best Skin Tightening"
    assert {p["url"] for p in posts} == {
        "https://glow.example/best-skin-tightening/",
        "https://glow.example/laser-hair-removal-cost/",
        "https://glow.example/old-post/",
    }


def test_enrich_merges_posts_and_counts_frequency():
    now = datetime.now(UTC)
    day = lambda n: (now - timedelta(days=n)).isoformat()
    sections = base_sections()
    site_crawl.enrich(
        sections,
        [HOME, "https://glow.example/blog/"],
        {},
        [
            {"url": "https://glow.example/a/", "title": "A", "published_at": day(10)},
            {"url": "https://glow.example/b/", "title": "B", "published_at": day(200)},
            {"url": "https://glow.example/c/", "title": "C", "published_at": day(400)},
            {"url": "https://glow.example/a", "title": "A again", "published_at": None},
        ],
    )
    blog = sections["site"]["blog"]
    assert blog["url"] == "https://glow.example/blog/"
    assert blog["post_count"] == 3
    assert blog["last_post_at"] == day(10)
    assert blog["posts_last6_months"] == 1 and blog["posts_last12_months"] == 2
    assert blog["posts"][0]["title"] == "A"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_embedded_images_keep_only_their_type():
    big = "data:image/png;base64," + "A" * 5000
    sections = site_audit.analyze(
        f'<html><body><img src="{big}"><img src="/a.jpg" alt="A"></body></html>', HOME
    )
    srcs = [i["src"] for i in sections["on_page"]["images"]["items"]]
    assert srcs == ["data:image/png;base64,", "https://glow.example/a.jpg"]


def test_gbp_links_finds_profile_and_review_links_in_the_pages():
    none = {
        HOME: '<a href="https://glow.example/contact">Contact</a><a href="https://instagram.com/glow">IG</a>'
    }
    assert site_crawl.gbp_links(none) == (False, False)
    profile = {
        HOME: '<footer><a href="https://maps.app.goo.gl/AbC123">Find us</a></footer>'
    }
    assert site_crawl.gbp_links(profile) == (True, False)
    review = {
        HOME: '<a href="https://glow.example/about">About</a>',
        "https://glow.example/reviews": '<a href="https://g.page/r/CaBcDe/review">Review us</a>',
    }
    assert site_crawl.gbp_links(review) == (True, True)
    write = {
        HOME: '<a href="https://search.google.com/local/writereview?placeid=X">Write</a>'
    }
    assert site_crawl.gbp_links(write) == (True, True)


GENERAL_SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://glow.example/about</loc><lastmod>2026-08-13T13:10:54+00:00</lastmod></url>
<url><loc>https://glow.example/blog</loc><lastmod>2026-09-21T00:00:00+00:00</lastmod></url>
<url><loc>https://glow.example/blog/psa-levels-by-age</loc><lastmod>2026-09-21T11:07:57+00:00</lastmod></url>
<url><loc>https://glow.example/blog/older-post</loc></url>
</urlset>"""

SITEMAP_INDEX = """<?xml version="1.0"?><sitemapindex>
<sitemap><loc>https://glow.example/page-sitemap.xml</loc></sitemap>
<sitemap><loc>https://glow.example/blog-sitemap.xml</loc></sitemap>
<sitemap><loc>https://other.example/blog-sitemap.xml</loc></sitemap>
</sitemapindex>"""


@pytest.mark.anyio
async def test_sitemap_posts_reads_a_general_sitemap_for_blog_posts(monkeypatch):
    async def fake_fetch(url, accept=("text/html",)):
        if url.endswith("/sitemap.xml"):
            return GENERAL_SITEMAP, url
        raise AppError(422, "site_unreachable", "missing")

    monkeypatch.setattr(site_crawl, "fetch_html", fake_fetch)
    posts = await site_crawl.sitemap_posts(HOME)
    # only /blog/<slug> pages count; /about and the /blog index do not
    assert [p["url"] for p in posts] == [
        "https://glow.example/blog/psa-levels-by-age",
        "https://glow.example/blog/older-post",
    ]
    # <lastmod> is the last-changed date, never the publish date
    assert posts[0]["published_at"] is None
    assert posts[0]["modified_at"].startswith("2026-09-21")
    assert posts[1]["published_at"] is None and posts[1]["modified_at"] is None


@pytest.mark.anyio
async def test_sitemap_posts_follows_a_sitemap_index_to_the_post_list(monkeypatch):
    asked = []

    async def fake_fetch(url, accept=("text/html",)):
        asked.append(url)
        if url.endswith("/sitemap_index.xml"):
            return SITEMAP_INDEX, url
        if url == "https://glow.example/blog-sitemap.xml":
            return GENERAL_SITEMAP.replace("/blog/", "/learn/"), url
        raise AppError(422, "site_unreachable", "missing")

    monkeypatch.setattr(site_crawl, "fetch_html", fake_fetch)
    posts = await site_crawl.sitemap_posts(HOME)
    # a child sitemap named like a post list is trusted, so any non-index page in it counts
    assert {p["url"] for p in posts} >= {"https://glow.example/learn/psa-levels-by-age"}
    # never fetches another site's sitemap, and the page sitemap is not a post list
    assert "https://other.example/blog-sitemap.xml" not in asked
    assert "https://glow.example/page-sitemap.xml" not in asked


# A footer built by JavaScript: its links are only text inside a <script> (Kajabi, Wix, ...).
JS_FOOTER = """<html><head><title>Men's Health Clinic | Healthy Aging</title></head><body>
<noscript><img src="https://www.facebook.com/tr?id=123&ev=PageView&noscript=1"></noscript>
<a href="https://www.youtube.com/watch?v=abc123">Watch</a>
<a href="https://www.youtube.com/@drpetteruti/videos">Episodes</a>
<script>
  footer.innerHTML = '<div class="footer-socials"><a href="https://www.facebook.com/IntellectualMedicine120"></a>'
   + '<a href="https://www.instagram.com/intellectualmedicine/"></a>'
   + '<a href="https://www.linkedin.com/in/drpetteruti/"></a>'
   + '<a href="https://twitter.com/share?url=x"></a><a href="https://www.facebook.com/sharer/sharer.php?u=x"></a>'
   + '</div><p><a href="tel:9543699079">954-369-9079</a></p><p>&copy; 2026 Intellectual Medicine. All rights reserved.</p>';
</script></body></html>"""


def test_socials_and_phone_are_found_when_the_footer_is_built_by_javascript():
    sections = site_audit.analyze(JS_FOOTER, "https://clinic.example/")
    socials = {s["network"]: s["url"] for s in sections["business"]["socials"]}
    assert socials["facebook"] == "https://www.facebook.com/IntellectualMedicine120"
    assert socials["instagram"] == "https://www.instagram.com/intellectualmedicine/"
    assert socials["linkedin"] == "https://www.linkedin.com/in/drpetteruti/"
    # the real link wins over the watch-page link; pixels and share buttons are never a profile
    assert socials["youtube"] == "https://www.youtube.com/@drpetteruti/videos"
    assert "tr?id" not in socials["facebook"] and "sharer" not in socials["facebook"]
    assert sections["business"]["nap"]["phone"] == "954-369-9079"


def test_brand_name_comes_from_structured_data_then_the_copyright_line():
    ld = '<script type="application/ld+json">{"@type":"MedicalBusiness","name":"Glow Med Spa"}</script>'
    assert site_crawl.brand_name(f"<html><head>{ld}</head></html>") == "Glow Med Spa"
    og = '<meta property="og:site_name" content="Radiance Clinic">'
    assert site_crawl.brand_name(f"<html><head>{og}</head></html>") == "Radiance Clinic"
    assert site_crawl.brand_name(JS_FOOTER) == "Intellectual Medicine"
    assert site_crawl.brand_name("<html><body>hello</body></html>") is None


def test_gbp_queries_put_names_first_and_the_domain_last():
    q = site_crawl.gbp_queries({"name": "Acme Wellness"}, JS_FOOTER, "clinic.example")
    assert q == [
        "Acme Wellness",
        "Intellectual Medicine",
        "954-369-9079",
    ]  # capped at 3
    assert site_crawl.gbp_queries({}, "<html></html>", "clinic.example") == [
        "clinic.example"
    ]
    # the same name from two sources is searched once
    assert (
        len(
            site_crawl.gbp_queries(
                {"name": "intellectual medicine"}, JS_FOOTER, "x.example"
            )
        )
        == 3
    )


def _apify(responses):
    """An httpx client whose Apify runs return the next list in `responses`."""
    asked = []

    def handler(request):
        import json

        asked.append(json.loads(request.content)["searchStringsArray"][0])
        return httpx.Response(201, json=responses[len(asked) - 1])

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), asked


UNRELATED = [
    {
        "title": "Other Clinic",
        "website": "https://other.example/",
        "phone": "(212) 555-1111",
    }
]
RIGHT = [
    {
        "title": "Intellectual Medicine",
        "website": "https://www.intellectualmedicine.com/",
        "phone": "(954) 369-9079",
        "totalScore": 5,
        "reviewsCount": 12,
        "url": "https://maps.example/p",
    }
]


@pytest.mark.anyio
async def test_gbp_lookup_tries_the_next_search_until_the_clinic_is_found():
    http, asked = _apify([UNRELATED, RIGHT, RIGHT])
    gbp, tried = await site_crawl.gbp_lookup(
        http,
        ["intellectualmedicine.com", "Intellectual Medicine", "954-369-9079"],
        "intellectualmedicine.com",
    )
    assert (
        gbp
        and gbp["name"] == "Intellectual Medicine"
        and gbp["found_by"] == "Intellectual Medicine"
    )
    assert gbp["match_reason"] == "website matches"
    assert (
        tried == asked == ["intellectualmedicine.com", "Intellectual Medicine"]
    )  # third never run


@pytest.mark.anyio
async def test_gbp_lookup_accepts_a_phone_match_when_the_listing_has_another_website():
    booking = [
        {
            "title": "Glow",
            "website": "https://booking.example/glow",
            "phone": "(512) 555-0000",
        }
    ]
    http, _ = _apify([booking])
    gbp, _ = await site_crawl.gbp_lookup(http, ["Glow"], "glow.example", "512-555-0000")
    assert gbp and gbp["match_reason"] == "phone matches"
    http, _ = _apify([booking])
    assert (await site_crawl.gbp_lookup(http, ["Glow"], "glow.example", None))[
        0
    ] is None


@pytest.mark.anyio
async def test_gbp_lookup_returns_none_and_what_it_tried_when_nothing_matches():
    http, asked = _apify([UNRELATED, UNRELATED, UNRELATED, UNRELATED])
    gbp, tried = await site_crawl.gbp_lookup(
        http, ["a", "b", "c", "d"], "clinic.example"
    )
    assert gbp is None and tried == asked == [
        "a",
        "b",
        "c",
    ]  # never more than three runs


# ---- post dates: read from the post pages, never assumed
def _post_page(meta="", head="", text=""):
    return f"<html><head>{head}</head><body>{meta}<article><h1>A post</h1><p>{text}</p></article></body></html>"


def test_published_reads_every_place_a_post_can_carry_its_date():
    meta = (
        '<meta property="article:published_time" content="2026-10-10T00:56:27+00:00">'
    )
    assert site_crawl._published(_post_page(head=meta)) == "2026-10-10T00:56:27+00:00"
    ld = '<script type="application/ld+json">{"@type":"BlogPosting","datePublished":"2026-03-04T09:00:00Z"}</script>'
    assert site_crawl._published(_post_page(head=ld)).startswith("2026-03-04")
    assert (
        site_crawl._published(_post_page(text="Posted on October 10, 2026 by Sam"))
        == "2026-10-10"
    )
    assert (
        site_crawl._published(_post_page(text="Published 5 Mar 2026")) == "2026-03-05"
    )
    assert site_crawl._published(_post_page(text="Sept. 9th, 2025")) == "2025-09-09"
    assert site_crawl._published(_post_page(text="no date here")) is None
    # a broken meta value is skipped in favour of the next source
    bad = '<meta property="article:published_time" content="soon">'
    assert (
        site_crawl._published(_post_page(head=bad, text="March 2, 2026"))
        == "2026-03-02"
    )
    # the footer's copyright year is not a publish date
    assert (
        site_crawl._published(
            "<html><body><article>hi</article><footer>March 2, 2020</footer></body></html>"
        )
        is None
    )


@pytest.mark.anyio
async def test_date_posts_reads_undated_posts_and_leaves_dated_ones(monkeypatch):
    asked = []

    async def fake_fetch(url, accept=("text/html",)):
        asked.append(url)
        if url.endswith("/broken"):
            raise AppError(422, "site_unreachable", "x")
        return _post_page(text="October 10, 2026"), url

    monkeypatch.setattr(site_crawl, "fetch_html", fake_fetch)
    posts = [
        {"url": "https://glow.example/blog/a", "title": "A", "published_at": None},
        {
            "url": "https://glow.example/blog/known",
            "title": "K",
            "published_at": "2025-01-01",
        },
        {"url": "https://glow.example/blog/broken", "title": "B", "published_at": None},
    ]
    await site_crawl.date_posts(posts)
    assert posts[0]["published_at"] == "2026-10-10"
    assert (
        posts[1]["published_at"] == "2025-01-01"
        and "https://glow.example/blog/known" not in asked
    )
    assert posts[2]["published_at"] is None  # a failed page is skipped, not fatal


@pytest.mark.anyio
async def test_date_posts_is_capped_and_cut_off_at_its_time_budget(monkeypatch):
    monkeypatch.setattr(site_crawl, "DATE_FETCHES", 5)
    asked = []

    async def fake_fetch(url, accept=("text/html",)):
        asked.append(url)
        return _post_page(text="October 10, 2026"), url

    monkeypatch.setattr(site_crawl, "fetch_html", fake_fetch)
    posts = [
        {"url": f"https://glow.example/blog/p{n}", "title": "", "published_at": None}
        for n in range(12)
    ]
    await site_crawl.date_posts(posts)
    assert len(asked) == 5 and sum(1 for p in posts if p["published_at"]) == 5

    async def slow_fetch(url, accept=("text/html",)):
        await asyncio.sleep(5)
        return _post_page(text="October 10, 2026"), url

    monkeypatch.setattr(site_crawl, "fetch_html", slow_fetch)
    monkeypatch.setattr(site_crawl, "DATE_BUDGET_S", 0.05)
    slow = [{"url": "https://glow.example/blog/s", "title": "", "published_at": None}]
    await site_crawl.date_posts(slow)  # returns after the budget, with nothing dated
    assert slow[0]["published_at"] is None


@pytest.mark.anyio
async def test_blog_posts_merges_url_posts_and_dates_them(monkeypatch):
    async def fake_fetch(url, accept=("text/html",)):
        if "sitemap" in url or url.endswith(".xml"):
            raise AppError(422, "site_unreachable", "no sitemap")
        return _post_page(
            head='<meta property="article:published_time" content="2026-09-01T00:00:00Z">'
        ), url

    monkeypatch.setattr(site_crawl, "fetch_html", fake_fetch)
    urls = [
        HOME,
        "https://glow.example/blogs/",
        "https://glow.example/blog/one",
        "https://glow.example/blog/two/",
    ]
    posts = await site_crawl.blog_posts(
        None, urls, {"https://glow.example/blogs/": "<html></html>"}, HOME
    )
    assert sorted(p["url"] for p in posts) == [
        "https://glow.example/blog/one",
        "https://glow.example/blog/two/",
    ]
    assert all(p["published_at"].startswith("2026-09-01") for p in posts)


def test_enrich_finds_a_plural_blog_index_and_reports_how_many_posts_have_dates():
    sections = base_sections()
    site_crawl.enrich(
        sections,
        [HOME, "https://glow.example/blogs/"],
        {},
        [
            {
                "url": "https://glow.example/blog/a",
                "title": "A",
                "published_at": "2026-10-10T00:00:00+00:00",
            },
            {"url": "https://glow.example/blog/b", "title": "B", "published_at": None},
            {"url": "https://glow.example/blog/c", "title": "C", "published_at": None},
        ],
    )
    blog = sections["site"]["blog"]
    assert blog["url"] == "https://glow.example/blogs/"
    assert blog["post_count"] == 3 and blog["dated_posts"] == 1


def test_a_gatsby_site_is_not_reported_as_wordpress():
    html = '<html><head><meta data-gatsby-head="true"></head><body><img src="/wp-content/a.jpg"></body></html>'
    assert site_audit.analyze(html, HOME)["site"]["platform"]["name"] == "Gatsby"
    assert (
        site_audit.analyze(
            '<html><body><img src="/wp-content/a.jpg"></body></html>', HOME
        )["site"]["platform"]["name"]
        == "WordPress"
    )


@pytest.mark.anyio
async def test_scrape_retries_once_on_a_passing_error_and_not_on_a_final_one(
    monkeypatch,
):
    monkeypatch.setattr(site_crawl.settings, "CRAWL_RETRY_DELAY_S", 0)
    calls = []

    def run(statuses):
        seq = iter(statuses)

        def respond(request):
            calls.append(request)
            status = next(seq)
            if status == "err":
                raise httpx.ConnectError("reset")
            body = {"data": {"rawHtml": RICH}} if status == 200 else {}
            return httpx.Response(status, json=body)

        return httpx.AsyncClient(transport=httpx.MockTransport(respond))

    async with run([503, 200]) as http:
        assert await site_crawl.scrape(http, f"{G}/a") == RICH and len(calls) == 2
    calls.clear()
    async with run(["err", 200]) as http:
        assert await site_crawl.scrape(http, f"{G}/a") == RICH and len(calls) == 2
    calls.clear()
    async with run([402, 200]) as http:  # out of credits: final, no second call
        assert await site_crawl.scrape(http, f"{G}/a") is None and len(calls) == 1
    calls.clear()
    async with run([503, 503, 200]) as http:  # one retry only
        assert await site_crawl.scrape(http, f"{G}/a") is None and len(calls) == 2


def test_a_page_keeps_the_text_of_its_first_menu_link():
    html = f"""<header><nav><ul><li><a href="{G}/menopause/">Menopause Treatment</a></li></ul></nav>
    <a href="{G}/menopause/">Perimenopause Quiz</a><a href="{G}/"></a><a href="{G}/">Home</a></header>"""
    top = site_crawl.nav_links(html, f"{G}/").top
    assert top[f"{G}/menopause/"] == "menopause treatment" and top[f"{G}/"] == "home"


def test_faq_sections_on_service_pages_count_as_an_faq_page_and_placeholders_are_listed():
    sections = base_sections()
    faq = "<html><body><h2>Frequently Asked Questions</h2><p>Sample Title</p></body></html>"
    plain = "<html><body><h2>Botox</h2></body></html>"
    site_crawl.enrich(
        sections, [f"{G}/iv", f"{G}/botox"], {f"{G}/iv": faq, f"{G}/botox": plain}
    )
    trust = {t["key"]: t for t in sections["site"]["trust"]}
    assert (
        trust["faq_page"]["status"] == "found" and trust["faq_page"]["url"] == f"{G}/iv"
    )
    assert (
        trust["faq_page"]["section"] is True
    )  # the link is a page with an FAQ section
    assert sections["site"]["placeholder_pages"] == [f"{G}/iv"]


def test_a_mega_menu_card_lists_every_service_not_only_the_known_ones():
    def card(slug: str, title: str, note: str) -> str:
        return (
            f'<a href="/category/{slug}"><div><div>{title}</div><p>{note}</p></div></a>'
        )

    cards = [
        ("facials", "Facials", "Restore your skin's natural glow."),
        ("peels", "Peels", "Get a customized plan."),
        ("lasers", "Lasers", "Advanced technology."),
        ("morpheus8", "Morpheus8", "Cosmetic microneedling."),
        ("botox", "Botox", "Learn more about our treatments."),
        ("liquid-bbl", "Liquid BBL", "The booty of your dreams."),
    ]
    html = (
        "<html><body><header><a href='/about'>About Us</a><a href='/contact'>Contact</a>"
        + "".join(card(*c) for c in cards)
        + "</header></body></html>"
    )
    menu = site_crawl.nav_links(html, f"{G}/")
    assert menu.top[f"{G}/category/peels"] == "peels"  # the description is not the name
    sections = base_sections()
    urls = [f"{G}/category/{c[0]}" for c in cards]
    site_crawl.enrich(sections, urls, {}, menu=menu)
    names = {c["service"] for c in sections["site"]["services"]["clusters"]}
    assert {"Peels", "Lasers", "Morpheus8", "Liquid Bbl"} <= names
    assert {
        "Neurotoxins",
        "Chemical Peels & Facials",
    } & names  # "about"/"restore" in a note is no veto


def test_a_menu_outside_nav_and_header_is_found_when_those_hold_too_few_links():
    items = "".join(f'<li><a href="{G}/t{i}/">Treatment {i}</a></li>' for i in range(8))
    html = f"""<html><body><header><a href="{G}/">Home</a></header>
    <div class="main-menu"><ul><li><a href="{G}/treatments/">Treatments</a><ul>{items}</ul></li></ul></div>
    <div class="footer-links"><a href="{G}/privacy/">Privacy</a></div></body></html>"""
    menu = site_crawl.nav_links(html, f"{G}/")
    assert len(menu.children) == 8 and set(menu.children.values()) == {"Treatments"}
    assert menu.parents == {f"{G}/treatments/": "Treatments"}


@pytest.mark.anyio
async def test_scrape_does_not_retry_a_rate_limit_that_says_to_wait_a_minute(
    monkeypatch,
):
    monkeypatch.setattr(site_crawl.settings, "CRAWL_RETRY_DELAY_S", 0)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": "60"}, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        assert await site_crawl.scrape(http, f"{G}/a") is None
    assert len(calls) == 1


@pytest.mark.anyio
async def test_a_site_that_blocks_direct_reads_gets_only_the_pages_the_firecrawl_plan_allows(
    monkeypatch,
):
    monkeypatch.setattr(site_crawl.settings, "FIRECRAWL_API_KEY", "fake")
    monkeypatch.setattr(site_crawl.settings, "FIRECRAWL_FALLBACKS", 2)
    read = []

    async def scrape(_http, url):
        read.append(url)
        return RICH

    async def no_map(_http, _url):
        return []

    monkeypatch.setattr(site_crawl, "scrape", scrape)
    monkeypatch.setattr(site_crawl, "map_site", no_map)
    _, pages, _, _ = await site_crawl.crawl(None, f"{G}/", MENU, "firecrawl", None)
    assert len(read) == 2 and len(pages) == 2


def test_script_text_inside_a_menu_link_is_not_the_link_text():
    html = f'<nav><a href="{G}/botox/"><script>var x = 1</script>Botox</a></nav>'
    assert site_crawl.nav_links(html, f"{G}/").top[f"{G}/botox/"] == "botox"


CARDS = f"""<html><body><header><nav><a href="{G}/#about">About</a><a href="{G}/#services">Services</a></nav></header>
<section><h2>Our services</h2>
<div><h4>Primary Care</h4><a href="{G}/primary-care">Learn more</a></div>
<div><h4>Chronic Conditions</h4><a href="{G}/chronic-conditions">Learn more</a></div></section>
<section><h2>Meet your provider</h2><div><h4>Dr. Jane</h4><a href="{G}/jane">Learn more</a></div></section></body></html>"""


def test_service_cards_on_the_home_page_join_the_menu_but_provider_cards_do_not():
    menu = site_crawl.nav_links(CARDS, f"{G}/")
    assert menu.top[f"{G}/primary-care"] == "primary care"
    assert menu.children[f"{G}/chronic-conditions"] == "Our services"
    assert f"{G}/jane" not in menu.top
    sections = base_sections()
    site_crawl.enrich(sections, list(menu.top), {}, None, menu)
    assert [c["service"] for c in sections["site"]["services"]["clusters"]] == [
        "Primary Care",
        "Chronic Conditions",
    ]


def test_a_service_word_in_a_post_a_category_or_the_home_page_is_no_service():
    menu = site_crawl.Menu(
        {f"{G}/menopause": "Services"},
        {},
        {
            f"{G}/botox": "botox",
            f"{G}/hormone-clinic": "contact",
            f"{G}/menopause": "menopause",
        },
    )
    urls = [
        f"{G}/",
        f"{G}/botox",
        f"{G}/hormone-clinic",
        f"{G}/menopause",
        f"{G}/did-someone-say-iv-therapy",
        f"{G}/category/emsculpt-neo",
    ]
    sections = base_sections()
    site_crawl.enrich(sections, urls, {}, None, menu)
    assert [c["service"] for c in sections["site"]["services"]["clusters"]] == [
        "Neurotoxins",
        "Menopause",
    ]


def test_without_a_readable_menu_a_short_top_level_page_can_still_be_a_service():
    sections = base_sections()
    urls = [f"{G}/botox", f"{G}/what-to-expect-with-first-botox-visit"]
    site_crawl.enrich(sections, urls, {}, None)
    assert [
        (c["service"], c["pages"]) for c in sections["site"]["services"]["clusters"]
    ] == [("Neurotoxins", [f"{G}/botox"])]


@pytest.mark.anyio
async def test_publish_date_comes_from_the_page_not_the_sitemap_lastmod(monkeypatch):
    """msintegrative.com: a post last edited 18 Dec 2025 was published 26 Sep 2025, and two staff
    bios kept as WordPress posts (category 'Our Providers') were edited 8 Oct 2025."""
    sitemap = """<urlset>
<url><loc>https://glow.example/numbers-matter/</loc><lastmod>2025-12-18T14:37:40+00:00</lastmod></url>
<url><loc>https://glow.example/jane-doe-fnp-c/</loc><lastmod>2025-10-08T21:06:13+00:00</lastmod></url>
</urlset>"""
    pages = {
        "https://glow.example/numbers-matter/": _post_page(
            head='<meta property="article:published_time" content="2025-09-26T21:04:54+00:00">'
            '<meta property="article:section" content="Blog">'
        ),
        "https://glow.example/jane-doe-fnp-c/": _post_page(
            head='<meta property="article:published_time" content="2025-03-26T16:23:20+00:00">'
            '<script type="application/ld+json">{"articleSection":["Our Providers"]}</script>'
        ),
    }

    async def fake_fetch(url, accept=("text/html",)):
        if url.endswith("/post-sitemap.xml"):
            return sitemap, url
        if url in pages:
            return pages[url], url
        raise AppError(422, "site_unreachable", "missing")

    monkeypatch.setattr(site_crawl, "fetch_html", fake_fetch)
    posts = await site_crawl.blog_posts(None, [HOME], {}, HOME)
    assert [p["url"] for p in posts] == ["https://glow.example/numbers-matter/"]
    assert posts[0]["published_at"].startswith("2025-09-26")


def test_json_ld_is_parsed_not_pattern_matched() -> None:
    nested = (
        '<script type="application/ld+json">{"@graph":[{"@type":"WebSite"},'
        '{"@type":"Article","datePublished":"2026-01-02","articleSection":'
        '["Our Team & Providers","Blog [news]"]}]}</script>'
    )
    assert site_crawl._section(nested) == "our team & providers blog [news]"
    assert site_crawl._published(nested) == "2026-01-02"
    broken = '<script type="application/ld+json">{"articleSection":"Blog",}</script>'
    assert site_crawl._section(broken) == "blog"
