import copy

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


def test_pick_pages_prioritizes_services_and_skips_home():
    picked = site_crawl.pick_pages(URLS, HOME)
    assert HOME not in picked
    assert picked[0].startswith("https://glow.example/services/")
    assert len(picked) <= site_crawl.MAX_PAGES


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
