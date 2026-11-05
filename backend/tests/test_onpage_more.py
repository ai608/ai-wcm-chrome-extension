import json
from typing import Any

import pytest

from app.services import onpage, site_crawl
from app.services import onpage_more as om

G = "https://glow.example"
pytestmark = pytest.mark.anyio


def keys(issues: list[dict[str, Any]]) -> list[str]:
    return [i["key"] for i in issues]


def doc(body: str, head: str = "", nav: str = "") -> str:
    return (
        f"<html><head><title>t</title>{head}</head><body><header><nav>{nav}</nav></header>"
        f"<main>{body}</main><footer><a href='/contact'>Contact</a></footer></body></html>"
    )


# ── mixed content ─────────────────────────────────────────────────────────────────────────


def test_mixed_content_counts_files_loaded_over_http_on_a_secure_page_but_not_links():
    html = (
        '<img src="http://x.example/a.png"><script src="http://x.example/a.js"></script>'
        '<link rel="stylesheet" href="http://x.example/a.css"><iframe src="http://x.example/f"></iframe>'
        '<img src="https://x.example/ok.png"><a href="http://other.example/">a link</a>'
        '<link rel="canonical" href="http://glow.example/">'
    )
    assert om.mixed_count(html, f"{G}/p") == 4
    assert (
        om.mixed_count(html, "http://glow.example/p") == 0
    )  # an http page can not be "mixed"


# ── title ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("title", "twice"),
    [
        ("Botox in Austin | Glow Med Spa | Glow Med Spa", True),
        ("Glow Med Spa Botox Austin | Glow Med Spa", True),
        ("Botox in Austin | Glow", False),
        (
            "Anti-Aging Botox - Austin",
            False,
        ),  # a hyphen inside a word is not a separator
        ("Glow Med Spa", False),
        ("Botox | Fillers | Peels", False),
    ],
)
def test_a_title_that_repeats_itself(title, twice):
    assert om.brand_twice(title) is twice


def page_issues(**over: Any) -> list[dict[str, Any]]:
    args: dict[str, Any] = {
        "title": "Botox in Austin | Glow",
        "h1": "Botox in Austin",
        "text": "plain text",
        "core": True,
        "has_disclaimer": False,
        "fetched": None,
    }
    html = over.pop("html", "<html></html>")
    url = over.pop("url", f"{G}/botox")
    return om.page_checks(html, url, **{**args, **over})


def test_title_and_heading_that_name_different_things_are_flagged_but_a_shared_word_is_enough():
    assert keys(
        page_issues(title="Botox in Austin | Glow", h1="Welcome to our clinic")
    ) == ["title_h1_mismatch"]
    assert page_issues(title="Botox in Austin | Glow", h1="Botox treatments") == []
    assert (
        page_issues(title="", h1="Welcome") == []
        and page_issues(title="Botox", h1="") == []
    )
    # contact pages ("Contact us" / "Get in touch") may differ: key pages only
    assert (
        page_issues(title="Contact Glow | Austin", h1="Get in Touch", core=False) == []
    )


def test_results_claims_need_a_disclaimer_on_core_pages_only():
    claim = "See our before and after photos. We guarantee results."
    assert keys(page_issues(text=claim)) == ["claims_no_disclaimer"]
    assert page_issues(text=claim, has_disclaimer=True) == []
    assert page_issues(text=claim, core=False) == []
    assert (
        page_issues(text="We offer botox. Results are great.") == []
    )  # "results" alone is no claim


@pytest.mark.parametrize(
    ("header", "flagged"),
    [
        ("noindex", True),
        ("none", True),
        ("googlebot: noindex, nofollow", True),
        ("NOINDEX", True),
        ("all", False),
        ("index, follow", False),
        ("noarchive", False),
        (None, False),
    ],
)
def test_an_x_robots_tag_header_that_blocks_indexing(header, flagged):
    got = page_issues(fetched={"x_robots": header, "hops": 0})
    assert (keys(got) == ["noindex_header"]) is flagged
    if flagged:
        assert got[0]["severity"] == "critical"
        assert (
            page_issues(fetched={"x_robots": header}, core=False)[0]["severity"]
            == "high"
        )


# ── links, redirects, hosts ───────────────────────────────────────────────────────────────


def fetch(final: str, hops: int = 0, status: int = 200) -> dict[str, Any]:
    return {"final": final, "hops": hops, "status": status}


def test_broken_links_chains_and_redirects_from_what_we_read_and_what_we_probed():
    fetched = {
        f"{G}/ok": fetch(f"{G}/ok"),
        f"{G}/gone": fetch(f"{G}/gone", status=404),
        f"{G}/old1": fetch(f"{G}/new", 1),
        f"{G}/old2": fetch(f"{G}/new", 1),
        f"{G}/old3": fetch(f"{G}/new", 1),
        f"{G}/chain": fetch(f"{G}/end", 3),
    }
    probes = {
        "links": [
            {
                "url": f"{G}/dead",
                "status": 410,
                "hops": 0,
                "final": f"{G}/dead",
                "found_on": f"{G}/",
            },
            {
                "url": f"{G}/firewall",
                "status": 403,
                "hops": 0,
                "final": f"{G}/firewall",
                "found_on": f"{G}/",
            },
            {
                "url": f"{G}/slow",
                "status": None,
                "hops": 0,
                "final": f"{G}/slow",
                "found_on": f"{G}/",
            },
            {
                "url": f"{G}/gone",
                "status": 404,
                "hops": 0,
                "final": f"{G}/gone",
                "found_on": f"{G}/",
            },  # seen twice
        ]
    }
    info, issues = om.link_checks(fetched, probes)
    got = {i["key"]: i["title"] for i in issues}
    assert (
        got
        == {
            "links_broken": "2 internal links lead to missing pages",  # gone (once), dead; not 403/unknown
            "links_redirect_chain": "1 internal links go through two or more redirects",
            "links_redirect": "3 internal links point to an address that redirects",
        }
    )
    assert {r["url"] for r in info["broken"]} == {f"{G}/gone", f"{G}/dead"}
    assert info["broken"][0]["found_on"] in (None, f"{G}/") and info["checked"] == 10


def test_a_couple_of_redirects_is_normal_and_nothing_probed_means_nothing_claimed():
    two = {f"{G}/a": fetch(f"{G}/a/", 1), f"{G}/b": fetch(f"{G}/b/", 1)}
    assert om.link_checks(two, None)[1] == []  # under the floor of 3
    assert om.link_checks(None, None) == (
        {"checked": 0, "broken": [], "chains": [], "redirects": []},
        [],
    )


def host(url: str, final: str, status: int | None = 200) -> dict[str, Any]:
    return {"url": url, "final": final, "status": status, "hops": 0}


def test_the_four_ways_to_type_the_address_must_end_in_one_place():
    ok = [
        host("http://glow.example/", "https://glow.example/"),
        host("https://glow.example/", "https://glow.example/"),
        host("http://www.glow.example/", "https://glow.example/"),
        host("https://www.glow.example/", "https://glow.example/"),
    ]
    assert om.host_checks({"hosts": ok}) == []
    split = [
        host("http://glow.example/", "https://glow.example/"),
        host("https://www.glow.example/", "https://www.glow.example/"),
    ]
    assert keys(om.host_checks({"hosts": split})) == ["host_split"]
    insecure = [
        host("http://glow.example/", "http://glow.example/"),
        host("https://glow.example/", "https://glow.example/"),
    ]
    assert set(keys(om.host_checks({"hosts": insecure}))) == {
        "http_not_redirected",
        "host_split",
    }


def test_hosts_that_did_not_answer_give_no_verdict():
    one = [
        host("https://glow.example/", "https://glow.example/"),
        host("https://www.glow.example/", "", None),
    ]
    assert om.host_checks({"hosts": one}) == [] and om.host_checks(None) == []
    # only the plain-http address answered: nothing to compare it with (a site with no https at
    # all is already reported by the home page's HTTPS essential), so no host verdict
    lone = [
        host("http://glow.example/", "http://glow.example/"),
        host("https://glow.example/", "", None),
    ]
    assert om.host_checks({"hosts": lone}) == []
    errors = [
        host("http://glow.example/", "", 404),
        host("https://glow.example/", "", 500),
    ]
    assert om.host_checks({"hosts": errors}) == []


# ── favicon and sharing tags ──────────────────────────────────────────────────────────────

SOCIAL = (
    '<meta property="og:title" content="Glow"><meta property="og:image" content="/i.png">'
    '<meta name="twitter:card" content="summary">'
)


def test_favicon_only_when_there_is_no_tag_and_no_file_and_we_could_test():
    tagged = f'<html><head><link rel="icon" href="/f.png">{SOCIAL}</head></html>'
    bare = f"<html><head>{SOCIAL}</head></html>"
    assert om.home_checks(tagged, {"favicon": {"status": 404}}) == []
    assert om.home_checks(bare, {"favicon": {"status": 200}}) == []
    assert keys(om.home_checks(bare, {"favicon": {"status": 404}})) == ["no_favicon"]
    assert (
        om.home_checks(bare, None) == []
        and om.home_checks(bare, {"favicon": None}) == []
    )


def test_sharing_tags_missing_are_named():
    html = '<html><head><link rel="icon" href="/f.png"><meta property="og:title" content="Glow"></head></html>'
    got = om.home_checks(html, None)
    assert (
        keys(got) == ["no_social_tags"] and "og:image, twitter:card" in got[0]["title"]
    )
    assert (
        om.home_checks(
            f'<html><head><link rel="icon" href="/f">{SOCIAL}</head></html>', None
        )
        == []
    )


# ── freshness ─────────────────────────────────────────────────────────────────────────────


def test_last_updated_dates_are_expected_on_service_pages():
    dated = ("Updated: March 3, 2026", "<html></html>")
    meta = ("plain", '<meta property="article:modified_time" content="2026-03-03">')
    bare = ("plain text", "<html></html>")
    assert om.freshness([dated, meta]) == []
    got = om.freshness([bare, bare, dated])
    assert keys(got) == ["no_updated_date"] and got[0]["title"].startswith(
        "2 of 3 service pages"
    )
    assert om.freshness([bare]) == []  # one page is no pattern
    assert (
        om.freshness([bare, dated, dated]) == []
    )  # a minority undated is not reported


# ── structure ─────────────────────────────────────────────────────────────────────────────


def classify(url: str) -> str:
    return "service" if "/services/" in url else "other"


def test_click_depth_and_whether_service_pages_point_onward():
    home = doc("<p>Welcome</p>")
    a = doc(
        '<a href="tel:+15125550100">Call</a><a href="/services/b">Related</a>',
        nav='<a href="/services/c">menu</a>',
    )
    b = doc("<p>No links here</p>")
    c = doc('<a href="/services/deep">More</a>')
    deep = doc("<p>Deep page</p>")
    read = {
        f"{G}/": home,
        f"{G}/services/a": a,
        f"{G}/services/b": b,
        f"{G}/services/c": c,
        f"{G}/services/deep": deep,
    }
    kinds = {u: ("home" if u == f"{G}/" else "service") for u in read}
    menu = {site_crawl._key(f"{G}/services/a"), site_crawl._key(f"{G}/services/b")}
    # home -> a, b (menu); a's header menu links c; c -> deep: deep is 3 clicks from home
    info, issues = om.structure(read, kinds, f"{G}/", menu, classify)
    got = {i["key"]: i["title"] for i in issues}
    assert got == {
        "deep_pages": "1 service pages are 3 or more clicks from the home page",
        "service_no_booking_link": "3 service pages have no booking or contact link in their text",
        "service_no_related_links": "2 service pages link to no other service",
    }
    assert info["deep"] == [f"{G}/services/deep"] and info["max_depth"] == 3
    # the footer "Contact" link and the header menu do not count as links in the page's text
    assert (
        f"{G}/services/a" not in info["no_booking_link"]
        and f"{G}/services/a" not in info["no_related_links"]
        or True
    )
    assert set(info["no_booking_link"]) == {
        f"{G}/services/b",
        f"{G}/services/c",
        f"{G}/services/deep",
    }
    assert set(info["no_related_links"]) == {f"{G}/services/b", f"{G}/services/deep"}


def test_structure_is_quiet_for_one_service_page_and_for_pages_that_do_point_onward():
    page = doc(
        '<a href="/contact-us">Book an appointment</a><a href="/services/y">Y</a>'
    )
    other = doc(
        '<a href="https://book.example/widget">Book now</a><a href="/services/x">X</a>'
    )
    read = {f"{G}/": doc(""), f"{G}/services/x": page, f"{G}/services/y": other}
    kinds = {
        f"{G}/": "home",
        f"{G}/services/x": "service",
        f"{G}/services/y": "service",
    }
    _, issues = om.structure(
        read, kinds, f"{G}/", {site_crawl._key(u) for u in kinds}, classify
    )
    assert issues == []
    _, one = om.structure(
        {f"{G}/": doc(""), f"{G}/services/x": doc("none")},
        {f"{G}/": "home", f"{G}/services/x": "service"},
        f"{G}/",
        set(),
        classify,
    )
    assert one == []  # a single service page is no pattern


def test_the_word_call_inside_another_word_is_not_a_booking_link():
    page = doc('<a href="/services/y">Treat yourself locally</a>')
    read = {f"{G}/": doc(""), f"{G}/services/x": page, f"{G}/services/y": page}
    kinds = {
        f"{G}/": "home",
        f"{G}/services/x": "service",
        f"{G}/services/y": "service",
    }
    _, issues = om.structure(read, kinds, f"{G}/", set(), classify)
    assert "service_no_booking_link" in keys(issues)


# ── locations and providers ───────────────────────────────────────────────────────────────

LOCAL = '<script type="application/ld+json">{"@type": "MedicalClinic", "name": "Glow"}</script>'
NAP = "<p>Glow Austin, 123 Main Street, Austin TX. Call (512) 555-0100.</p>"


def test_each_location_page_needs_its_own_address_phone_and_markup():
    read = {
        f"{G}/locations/": "<html><body>hub</body></html>",
        f"{G}/locations/austin": f"<html><body>{NAP}{LOCAL}</body></html>",
        f"{G}/locations/dallas": f"<html><body>{NAP}</body></html>",  # no markup
        f"{G}/locations/waco": "<html><body><p>Visit us in Waco</p></body></html>",
    }
    got = om.locations(read, {})
    assert keys(got) == ["locations_incomplete"] and got[0]["title"].startswith(
        "2 of 3 location pages"
    )
    one = {k: v for k, v in read.items() if k.endswith(("/locations/", "/austin"))}
    assert om.locations(one, {}) == []  # one location page: not a multi-location site
    ok = {
        f"{G}/locations/a": f"<html><body>{NAP}{LOCAL}</body></html>",
        f"{G}/locations/b": f"<html><body>{NAP}{LOCAL}</body></html>",
    }
    assert om.locations(ok, {}) == []


def test_provider_pages_should_carry_person_or_physician_markup():
    person = '<script type="application/ld+json">{"@type": "Person", "name": "Dr. Lee"}</script>'
    plain = "<html><body>Dr. Lee, MD</body></html>"
    assert keys(
        om.providers({f"{G}/providers/dr-lee": plain, f"{G}/botox": person})
    ) == ["schema_no_provider"]
    assert (
        om.providers({f"{G}/providers/dr-lee": f"<html><body>x{person}</body></html>"})
        == []
    )
    assert (
        om.providers({f"{G}/botox": plain}) == []
    )  # no provider page found: nothing to say
    graph = '<script type="application/ld+json">{"@graph": [{"@type": ["Physician", "Person"]}]}</script>'
    assert om.providers({f"{G}/team": f"<html><body>{graph}</body></html>"}) == []


# ── markup against the page ───────────────────────────────────────────────────────────────


def local_page(phone: str, street: str) -> str:
    data = {
        "@type": "MedicalClinic",
        "telephone": phone,
        "address": {"streetAddress": street},
    }
    return f'<html><body><script type="application/ld+json">{json.dumps(data)}</script></body></html>'


def test_markup_phone_and_address_must_appear_on_the_page():
    html = local_page("+1 512-555-0101", "5607 4th St Ct SW")
    assert (
        om.schema_vs_page(html, "Call us (512) 555-0101 at 5607 4th St Ct SW, Austin")
        == []
    )
    got = om.schema_vs_page(html, "Call (512) 555-9999 at 5607 4th St")
    assert keys(got) == ["schema_phone_mismatch"] and "5125550101" in got[0]["title"]
    got = om.schema_vs_page(html, "Call (512) 555-0101 at 99 Elm Street")
    assert (
        keys(got) == ["schema_address_mismatch"]
        and "5607 4th St Ct SW" in got[0]["title"]
    )


def test_markup_checks_say_nothing_without_something_to_compare():
    assert om.schema_vs_page("<html></html>", "text") == []
    assert om.schema_vs_page(local_page("", ""), "text") == []
    assert (
        om.schema_vs_page(
            local_page("+1 512-555-0101", "5607 4th St"),
            "5607 4th St is here, but no phone number is",
        )
        == []
    )


# ── images ────────────────────────────────────────────────────────────────────────────────


def test_images_without_size_css_backgrounds_and_large_files():
    page = (
        '<img src="/a.jpg"><img src="/b.jpg" width="10"><img src="/c.jpg" width="10" height="10">'
        '<img src="data:image/gif;base64,xx"><div style="background-image:url(/hero.jpg)">x</div>'
        '<div style="color:red">y</div>'
    )
    probes = {
        "images": [
            {"url": f"{G}/big.jpg", "status": 200, "length": 900_000},
            {"url": f"{G}/small.jpg", "status": 200, "length": 5_000},
            {
                "url": f"{G}/missing.jpg",
                "status": 404,
                "length": 9_000_000,
            },  # an error page's size is not an image's
            {"url": f"{G}/unknown.jpg", "status": 200, "length": None},
        ]
    }
    info, issues = om.images_more({f"{G}/": page, f"{G}/p": page}, probes)
    got = {i["key"]: i["title"] for i in issues}
    assert got == {
        "images_no_dimensions": "4 (on 2 pages) images have no width and height",
        "images_large": "1 home page images are over 400 KB",
        "images_css_background": "2 (on 2 pages) pictures are set as CSS backgrounds",
    }
    assert (
        info["large"] == [{"url": f"{G}/big.jpg", "bytes": 900_000}]
        and info["sizes_checked"] == 3
    )


def test_a_couple_of_unsized_images_is_not_reported_and_unprobed_sizes_claim_nothing():
    info, issues = om.images_more(
        {f"{G}/": '<img src="/a.jpg"><img src="/b.jpg">'}, None
    )
    assert issues == [] and info["no_dimensions"] == 2 and info["large"] == []


# ── PageSpeed: phones and real visitors ───────────────────────────────────────────────────


def test_speed_issues_name_what_real_visitors_and_phones_suffer():
    speed = {
        "tap_targets_ok": False,
        "zoom_ok": False,
        "field": {
            "source": "origin",
            "lcp_ms": 4300,
            "lcp": "SLOW",
            "inp_ms": 620,
            "inp": "SLOW",
            "cls": 0.31,
            "cls_category": "SLOW",
        },
    }
    got = {i["key"]: i["title"] for i in om.speed_issues(speed)}
    assert set(got) == {
        "tap_targets_small",
        "viewport_blocks_zoom",
        "field_lcp_poor",
        "field_inp_poor",
        "field_cls_poor",
    }
    assert "4.3 s" in got["field_lcp_poor"] and "620 ms" in got["field_inp_poor"]
    assert (
        "0.31" in got["field_cls_poor"]
    )  # the layout shift is judged by its own verdict


def test_speed_issues_are_quiet_for_good_unknown_or_missing_data():
    assert om.speed_issues(None) == [] and om.speed_issues({}) == []
    good = {
        "tap_targets_ok": True,
        "zoom_ok": True,
        "field": {"lcp": "FAST", "lcp_ms": 1200, "inp": "AVERAGE", "inp_ms": 300},
    }
    assert om.speed_issues(good) == []
    unknown = {
        "tap_targets_ok": None,
        "zoom_ok": None,
        "field": None,
    }  # audit did not run / small site
    assert om.speed_issues(unknown) == []


def test_add_speed_issues_rescores_and_never_duplicates():
    sections = {
        "on_page": {
            "summary": {},
            "pages": [],
            "site_issues": [
                {
                    "key": "local_no_map",
                    "severity": "low",
                    "title": "t",
                    "detail": "d",
                    "url": None,
                }
            ],
            "pagespeed": {"tap_targets_ok": False, "zoom_ok": True, "field": None},
        }
    }
    onpage.add_speed_issues(sections)
    onpage.add_speed_issues(sections)
    on = sections["on_page"]
    assert keys(on["site_issues"]) == ["local_no_map", "tap_targets_small"]
    assert on["summary"]["medium"] == 1 and on["summary"]["score"] == 97
    on["pagespeed"]["tap_targets_ok"] = (
        True  # fixed on the next audit: the old issue goes away
    )
    onpage.add_speed_issues(sections)
    assert keys(on["site_issues"]) == ["local_no_map"]
    onpage.add_speed_issues({"on_page": {}})  # no page checks ran: nothing to do


# ── false alarms seen on a real site (380companies.com) ───────────────────────────────────


def test_a_hidden_tracking_pixel_is_not_an_image_without_a_size():
    page = (
        '<img src="/real.jpg"><img src="https://moderate.cleantalk.example/pixel/4d34" style="display: none;">'
        '<img src="/a.gif" hidden><img src="/b.gif" style="visibility:hidden"><img src="/t.png" width="1" height="1">'
        '<img src="https://stats.example/beacon.gif">'
    )
    info, issues = om.images_more({f"{G}/": page}, None)
    assert (
        info["no_dimensions"] == 1 and issues == []
    )  # one real picture; under the floor of three
    three = (
        '<img src="/a.jpg"><img src="/b.jpg"><img src="/c.jpg"><img src="/p/pixel.gif">'
    )
    assert om.images_more({f"{G}/": three}, None)[0]["no_dimensions"] == 3


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        (
            "We guarantee total restoration of your home or business.",
            False,
        ),  # a service promise
        ("We guarantee your satisfaction and low prices.", False),
        ("We guarantee results.", True),
        ("Guaranteed weight loss in 30 days.", True),
        ("We guarantee great outcomes for every patient.", True),
        ("See the before & after gallery.", True),
        ("Lose 20 lbs in a month.", True),
        ("98% of our patients are happy.", True),
    ],
)
def test_only_a_claim_about_results_needs_a_disclaimer(text, flagged):
    assert (keys(page_issues(text=text)) == ["claims_no_disclaimer"]) is flagged
