"""Adversarial cases for area grading, hub detection and how `apply` merges them.
These run on messy pages and odd inputs: the code must never crash, and must not invent
problems (a page flagged as a copy of itself, one page counted twice, a menu read as a hub)."""

import random
import time

import pytest

from app.services import area_pages, site_ai, site_audit, site_crawl

HOME = "https://x.com"


def words(prefix: str, city: str = "", n: int = 320) -> str:
    return " ".join(
        f"{prefix}{i} {city}" if city and i % 10 == 0 else f"{prefix}{i}"
        for i in range(n)
    )


def page(title="T", h1="H", text="", head="", before="", after="") -> str:
    return (
        f"<html><head><title>{title}</title>{head}</head><body>{before}"
        f"<h1>{h1}</h1><main><p>{text}</p></main>{after}</body></html>"
    )


def grade(areas, pages, urls=None):
    out = area_pages.grade(areas, urls if urls is not None else list(pages), pages)
    return {g["name"]: g for g in out}


# ── pages counted wrongly ─────────────────────────────────────────────────────────────────


def test_one_page_for_two_cities_is_not_a_copy_of_itself():
    both = page("Tampa and Clearwater", "Tampa and Clearwater", words("w", "Tampa"))
    g = grade(["Tampa", "Clearwater"], {f"{HOME}/bay/": both})
    assert g["Tampa"]["issues"] == [] and g["Clearwater"]["issues"] == []
    assert g["Tampa"]["status"] == g["Clearwater"]["status"] == "covered"


def test_the_same_page_under_two_spellings_counts_once():
    tampa = page("Tampa", "Tampa", words("w"))
    pages = {f"{HOME}/tampa": tampa}  # what was crawled
    urls = [
        f"{HOME}/tampa/",
        "https://www.x.com/tampa/",
        f"{HOME}/tampa",
    ]  # what was mapped
    g = grade(["Tampa"], pages, urls)["Tampa"]
    assert len(g["pages"]) == 1


def test_a_mapped_spelling_still_finds_the_crawled_page_to_judge():
    thin = page("Tampa", "Tampa", "tiny")
    g = grade(["Tampa"], {f"{HOME}/tampa": thin}, [f"{HOME}/tampa/"])["Tampa"]
    assert g["issues"] == [
        "thin"
    ]  # judged although the map spelled the address differently


def test_the_same_area_twice_in_the_list_is_one_entry():
    out = area_pages.grade(["Tampa", "tampa", " Tampa "], [], {})
    assert [g["name"] for g in out] == ["Tampa"]


def test_accented_names_match_plain_addresses():
    g = grade(["San José"], {}, [f"{HOME}/san-jose/"])["San José"]
    assert g["status"] == "covered"


# ── what a page "says" ────────────────────────────────────────────────────────────────────


def test_h1_inside_a_header_still_counts_for_the_title_and_heading_check():
    hero = "<header><h1>Weight loss in Tampa</h1></header>"
    p = f"<html><head><title>Tampa</title></head><body>{hero}<main>{words('w')}</main></body></html>"
    g = grade(["Tampa"], {f"{HOME}/x/": p})["Tampa"]
    assert g["status"] == "covered"  # own page by title and H1, both found


def test_menu_and_footer_words_do_not_make_a_thin_page_look_full():
    boiler = "<nav>" + words("menu", n=250) + "</nav>"
    foot = "<footer>" + words("foot", n=250) + "</footer>"
    p = page("Tampa", "Tampa", "A few words about Tampa.", before=boiler, after=foot)
    assert grade(["Tampa"], {f"{HOME}/tampa/": p})["Tampa"]["issues"] == ["thin"]


def test_a_layout_with_no_landmarks_is_not_called_thin_for_having_none():
    plain = f"<html><head><title>Tampa</title></head><body><div><h1>Tampa</h1>{words('w')}</div></body></html>"
    assert grade(["Tampa"], {f"{HOME}/tampa/": plain})["Tampa"]["issues"] == []


def test_content_wrapped_in_a_header_is_not_called_thin():
    wrapped = f"<html><head><title>Tampa</title></head><body><header><h1>Tampa</h1>{words('w')}</header></body></html>"
    assert grade(["Tampa"], {f"{HOME}/tampa/": wrapped})["Tampa"]["issues"] == []


def test_boilerplate_shared_by_every_page_does_not_make_cities_copies():
    boiler = "<footer>" + words("foot", n=400) + "</footer>"
    a = page(
        "Tampa",
        "Tampa",
        "Short unique text about Tampa " + words("a", n=40),
        after=boiler,
    )
    b = page(
        "Ocala",
        "Ocala",
        "Other unique text about Ocala " + words("b", n=40),
        after=boiler,
    )
    g = grade(["Tampa", "Ocala"], {f"{HOME}/tampa/": a, f"{HOME}/ocala/": b})
    assert "duplicate" not in g["Tampa"]["issues"]


def test_an_area_in_the_footer_only_is_mentioned_not_covered():
    p = page(
        "Home", "Home", words("w"), after="<footer>Serving Tampa and Ocala</footer>"
    )
    assert grade(["Tampa"], {f"{HOME}/": p})["Tampa"]["status"] == "mentioned"


def test_whole_words_only():
    p = page("Home", "Home", "We love Tampanese food and Stampa prints " + words("w"))
    assert grade(["Tampa"], {f"{HOME}/": p})["Tampa"]["status"] == "missing"


@pytest.mark.parametrize(
    "name", ["St. (Pete)", "A+B", "Coeur d'Alene", "C++", "[x]", "a|b", "\\d+", "."]
)
def test_names_with_regex_characters_do_not_break_matching(name):
    p = page("Home", "Home", f"We serve {name} too " + words("w"))
    g = grade([name], {f"{HOME}/": p})[name]
    assert g["status"] in ("mentioned", "missing", "covered")


@pytest.mark.parametrize(
    "junk",
    [
        "",
        "   ",
        "<html",
        "<<<>>>",
        "plain markdown # Tampa\n\n- item",
        "\x00\x01",
        "<title>",
        "<h1>",
    ],
)
def test_unreadable_pages_never_crash(junk):
    g = grade(["Tampa"], {f"{HOME}/tampa/": junk})["Tampa"]
    assert g["status"] in ("covered", "needs_work")


def test_no_areas_no_pages():
    assert area_pages.grade([], [], {}) == []


def test_blog_urls_and_blog_titles_are_never_an_areas_page():
    pages = {f"{HOME}/blog/x/": page("Tampa", "Tampa", words("w"))}
    assert grade(["Tampa"], pages)["Tampa"]["status"] == "mentioned"


# ── hub detection ─────────────────────────────────────────────────────────────────────────


def hub(pages, cities):
    return site_ai._is_area_hub(pages, cities)


CITIES = [f"{HOME}/tampa/", f"{HOME}/ocala/", f"{HOME}/miami/"]


def with_menu(menu: str, body: str = "hi") -> str:
    return f"<html><body>{menu}<main>{body}</main></body></html>"


def test_a_menu_that_is_not_a_nav_tag_does_not_make_every_page_a_hub():
    menu = '<div class="menu"><a href="/tampa/">T</a><a href="/ocala/">O</a><a href="/miami/">M</a></div>'
    pages = {f"{HOME}/": with_menu(menu)} | {
        f"{HOME}/p{i}/": with_menu(menu, f"page {i}") for i in range(6)
    }
    assert hub(pages, CITIES) is False


def test_a_real_hub_is_still_found_when_the_site_has_a_div_menu():
    menu = '<div class="menu"><a href="/tampa/">T</a><a href="/ocala/">O</a><a href="/miami/">M</a></div>'
    body = '<a href="/tampa/">T</a> <a href="/ocala/">O</a>'
    pages = {f"{HOME}/": with_menu(menu)} | {
        f"{HOME}/p{i}/": with_menu(menu, f"page {i}") for i in range(6)
    }
    pages[f"{HOME}/areas/"] = with_menu(menu, body)
    assert hub(pages, CITIES) is True


def test_links_to_another_site_with_the_same_path_are_not_city_pages():
    body = '<a href="https://other.com/tampa/">T</a> <a href="https://other.com/ocala/">O</a>'
    assert hub({f"{HOME}/areas/": with_menu("", body)}, CITIES) is False


def test_relative_and_odd_links_are_handled():
    body = '<a href="../tampa/">T</a><a href="ocala">O</a><a href="mailto:a@b.c">m</a><a>no href</a><a href="">e</a><a href="#top">h</a>'
    assert (
        hub(
            {f"{HOME}/areas/x/": with_menu("", body)},
            [f"{HOME}/areas/tampa/", f"{HOME}/areas/x/ocala/"],
        )
        is True
    )


def test_a_page_linking_itself_and_one_city_is_no_hub():
    body = '<a href="/areas/">me</a><a href="/tampa/">T</a>'
    assert hub({f"{HOME}/areas/": with_menu("", body)}, CITIES) is False


def test_hub_check_survives_junk_pages():
    assert (
        hub(
            {f"{HOME}/a/": "", f"{HOME}/b/": "\x00<<<", f"{HOME}/c/": "# markdown"},
            CITIES,
        )
        is False
    )


# ── apply: merging into the audit ─────────────────────────────────────────────────────────


def fresh_sections():
    s = site_audit.analyze(
        "<html><head><title>G</title></head><body><h1>G</h1></body></html>", HOME + "/"
    )
    site_crawl.enrich(s, [HOME + "/"], {})
    s["site"]["cities"].update(city_pages=[], pages_found=0, hub_page=False)
    return s


def test_apply_twice_gives_the_same_result():
    pages = {f"{HOME}/tampa/": page("Tampa", "Tampa", words("w"))}
    s = fresh_sections()
    ai = {"areas_served": ["Tampa", "Ocala"]}
    site_ai.apply(s, ai, pages, list(pages))
    once = repr(s["site"]["cities"])
    site_ai.apply(s, ai, pages, list(pages))
    assert repr(s["site"]["cities"]) == once


def test_city_pages_are_not_counted_twice_across_spellings():
    s = fresh_sections()
    s["site"]["cities"].update(city_pages=[f"{HOME}/locations/tampa"], pages_found=1)
    pages = {f"{HOME}/locations/tampa/": page("Tampa", "Tampa", words("w"))}
    site_ai.apply(s, {"areas_served": ["Tampa"]}, pages, list(pages))
    assert s["site"]["cities"]["pages_found"] == 1


def test_apply_without_any_areas_keeps_what_the_crawl_found():
    s = fresh_sections()
    s["site"]["cities"].update(
        city_pages=[f"{HOME}/locations/x"], pages_found=1, hub_page=True
    )
    site_ai.apply(s, {"areas_served": None}, {}, [])
    c = s["site"]["cities"]
    assert c["pages_found"] == 1 and c["hub_page"] is True and c["areas"] == []
    assert c["claimed_not_built"] == []


def test_claimed_not_built_is_exactly_the_areas_without_a_page_of_their_own():
    pages = {
        f"{HOME}/": page("G", "G", words("w") + " Ocala"),
        f"{HOME}/tampa/": page("Tampa", "Tampa", words("t")),
    }
    s = fresh_sections()
    site_ai.apply(s, {"areas_served": ["Tampa", "Ocala", "Miami"]}, pages, list(pages))
    c = s["site"]["cities"]
    by = {a["name"]: a["status"] for a in c["areas"]}
    assert by == {"Tampa": "covered", "Ocala": "mentioned", "Miami": "missing"}
    assert c["claimed_not_built"] == ["Ocala", "Miami"]


def test_the_home_page_can_be_a_citys_own_page_without_becoming_a_counted_city_page():
    pages = {f"{HOME}/": page("Glow Med Spa Tampa", "Tampa med spa", words("w"))}
    s = fresh_sections()
    site_ai.apply(s, {"areas_served": ["Tampa"]}, pages, list(pages))
    c = s["site"]["cities"]
    assert c["areas"][0]["status"] == "covered"
    assert c["pages_found"] == 0 and c["claimed_not_built"] == []


def test_the_result_is_plain_json():
    import json

    pages = {f"{HOME}/tampa/": page("Tampa", "Tampa", words("w"))}
    s = fresh_sections()
    site_ai.apply(s, {"areas_served": ["Tampa", "Ocala"]}, pages, list(pages))
    json.dumps(s["site"]["cities"])


# ── random input and speed ────────────────────────────────────────────────────────────────

POOL = [
    "Tampa",
    "St. Petersburg",
    "Florida",
    "San José",
    "A+B",
    "Coeur d'Alene",
    "x",
    "Round Rock",
    "O'Fallon",
    "Naples",
]
FRAGMENTS = [
    "<nav>",
    "</nav>",
    "<h1>",
    "</h1>",
    "<title>",
    "</title>",
    "<main>",
    "Tampa",
    "St. Petersburg",
    " word ",
    "<a href='/tampa/'>",
    "</a>",
    "<footer>",
    "<meta name=robots content=noindex>",
    "<script>x</script>",
    "&amp;",
    "<<",
    "\x00",
]


def noise(rng: random.Random) -> str:
    return "".join(rng.choice(FRAGMENTS) for _ in range(rng.randint(0, 40))) + words(
        "n", n=rng.choice([0, 5, 400])
    )


@pytest.mark.parametrize("seed", range(40))
def test_random_pages_and_areas_never_crash_and_keep_their_promises(seed):
    rng = random.Random(seed)
    areas = [rng.choice(POOL) for _ in range(rng.randint(0, 8))]
    slugs = [
        "tampa",
        "st-petersburg",
        "florida",
        "san-jose",
        "round-rock",
        "blog/tampa",
        "x",
        "",
    ]
    urls = [f"{HOME}/{rng.choice(slugs)}/" for _ in range(rng.randint(0, 8))]
    pages = {u: noise(rng) for u in urls if rng.random() < 0.7}
    out = area_pages.grade(areas, urls, pages)
    names = [g["name"] for g in out]
    assert len(names) == len({n.lower() for n in names})  # no area twice
    for g in out:
        assert g["status"] in ("covered", "needs_work", "mentioned", "missing")
        assert set(g["issues"]) <= {"noindex", "thin", "title_h1", "duplicate"}
        assert (g["status"] == "needs_work") == bool(g["issues"] and g["pages"])
        assert (g["status"] == "missing") == (
            not g["pages"] and g["status"] != "mentioned"
        )
        if g["status"] in ("covered", "needs_work"):
            assert g["pages"]
        assert ("duplicate" in g["issues"]) == (g["duplicate_of"] is not None)
        assert g["duplicate_of"] != g["name"]
    site_ai._is_area_hub(pages, urls)  # must not raise either


def test_sixty_pages_and_twenty_areas_stay_fast():
    areas = [f"City{i}" for i in range(20)]
    pages = {
        f"{HOME}/city{i % 20}-{i}/": page(
            f"City{i % 20}", f"City{i % 20}", words("w", f"City{i % 20}", 600)
        )
        for i in range(60)
    }
    started = time.monotonic()
    out = area_pages.grade(areas, list(pages), pages)
    site_ai._is_area_hub(pages, list(pages))
    assert len(out) == 20
    assert time.monotonic() - started < 3.0


# ── more hub and markup cases ─────────────────────────────────────────────────────────────


def bare(menu: str, body: str = "hi") -> str:
    """A page with no <main> and a menu made of plain divs."""
    return f"<html><body><div class='top'>{menu}</div><div class='content'>{body}</div></body></html>"


DIV_MENU = '<a href="/tampa/">T</a><a href="/ocala/">O</a><a href="/miami/">M</a>'


def test_no_main_and_a_div_menu_on_every_page_is_no_hub():
    pages = {f"{HOME}/": bare(DIV_MENU)} | {
        f"{HOME}/p{i}/": bare(DIV_MENU, f"page {i}") for i in range(6)
    }
    assert hub(pages, CITIES) is False


def test_no_main_a_hub_that_links_cities_the_menu_does_not():
    menu = '<a href="/tampa/">T</a>'
    pages = {f"{HOME}/": bare(menu)} | {
        f"{HOME}/p{i}/": bare(menu, f"page {i}") for i in range(6)
    }
    pages[f"{HOME}/areas/"] = bare(
        menu, '<a href="/ocala/">O</a> <a href="/miami/">M</a>'
    )
    assert hub(pages, CITIES) is True


def test_a_small_site_with_no_main_still_finds_its_hub():
    pages = {
        f"{HOME}/": bare(""),
        f"{HOME}/areas/": bare("", '<a href="/tampa/">T</a><a href="/ocala/">O</a>'),
    }
    assert hub(pages, CITIES) is True


def test_nav_inside_header_and_header_inside_nav_do_not_crash_or_leak_links():
    nested = (
        '<header><nav><a href="/tampa/">T</a><a href="/ocala/">O</a></nav></header>'
        '<nav><header><a href="/miami/">M</a></header></nav><main>nothing here</main>'
    )
    assert hub({f"{HOME}/p/": f"<html><body>{nested}</body></html>"}, CITIES) is False
    g = grade(
        ["Tampa"],
        {
            f"{HOME}/tampa/": f"<html><head><title>Tampa</title></head><body>{nested}{words('w')}</body></html>"
        },
    )
    assert g["Tampa"]["status"] in ("covered", "needs_work")


def test_www_and_scheme_differences_between_a_link_and_a_page_do_not_hide_a_hub():
    cities = ["https://www.x.com/tampa/", "https://www.x.com/ocala"]
    body = '<a href="http://x.com/tampa">T</a><a href="https://x.com/ocala/">O</a>'
    assert hub({"https://x.com/areas/": with_menu("", body)}, cities) is True


def test_apply_with_no_pages_and_no_urls_does_not_crash():
    s = fresh_sections()
    site_ai.apply(s, {"areas_served": ["Tampa"]}, {}, None)
    assert s["site"]["cities"]["areas"][0]["status"] == "missing"
    assert s["site"]["cities"]["claimed_not_built"] == ["Tampa"]


def test_an_old_keyword_city_page_still_counts_for_its_area():
    s = fresh_sections()
    s["site"]["cities"].update(city_pages=[f"{HOME}/locations/austin"], pages_found=1)
    site_ai.apply(s, {"areas_served": ["Austin"]}, {}, [])
    assert s["site"]["cities"]["claimed_not_built"] == []
    assert s["site"]["cities"]["pages_found"] == 1


def test_more_than_fifty_city_pages_are_capped():
    urls = [f"{HOME}/areas/city{i}/" for i in range(80)]
    s = fresh_sections()
    site_ai.apply(s, {"areas_served": [f"City{i}" for i in range(20)]}, {}, urls)
    assert len(s["site"]["cities"]["city_pages"]) <= 50
    assert len(s["site"]["cities"]["claimed_not_built"]) <= 20


@pytest.mark.parametrize("seed", range(300))
def test_apply_keeps_its_promises_on_random_sites(seed):
    """Whatever the site looks like: nothing crashes, numbers agree with lists, a second run
    changes nothing, and `claimed_not_built` is exactly the areas without a page of their own."""
    rng = random.Random(1000 + seed)
    areas = [rng.choice(POOL) for _ in range(rng.randint(0, 10))]
    slugs = [
        "tampa",
        "st-petersburg",
        "florida",
        "san-jose",
        "round-rock",
        "blog/tampa",
        "x",
        "locations/naples",
        "a/b/c",
    ]
    spell = [
        lambda u: u,
        lambda u: u.rstrip("/"),
        lambda u: u.replace("https://x.com", "https://www.x.com"),
    ]
    urls = [
        rng.choice(spell)(f"{HOME}/{rng.choice(slugs)}/")
        for _ in range(rng.randint(0, 12))
    ]
    pages = {u: noise(rng) for u in urls if rng.random() < 0.6}
    s = fresh_sections()
    ai = {"areas_served": areas}
    site_ai.apply(s, ai, pages, urls)
    c = s["site"]["cities"]
    first = repr(c)
    assert c["pages_found"] == len(c["city_pages"]) <= 50
    assert len({area_pages.norm(u) for u in c["city_pages"]}) == len(
        c["city_pages"]
    )  # one per page
    by = {a["name"]: a["status"] for a in c["areas"]}
    assert (
        c["claimed_not_built"]
        == [n for n, st in by.items() if st in ("mentioned", "missing")][:20]
    )
    assert set(c["claimed_not_built"]) <= set(by)
    assert isinstance(c["hub_page"], bool)
    site_ai.apply(s, ai, pages, urls)
    assert repr(s["site"]["cities"]) == first


# ── found on real sites ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "claimed",
    ["Austin, TX", "Austin, Texas", "Austin (TX)", "Austin,TX", " Austin , TX "],
)
def test_a_claimed_area_with_a_state_still_meets_its_page(claimed):
    pages = {f"{HOME}/austin/": page("Med spa in Austin", "Austin", words("w"))}
    assert grade([claimed], pages)[claimed.strip()]["status"] == "covered"
    other = {f"{HOME}/spa/": page("Austin med spa", "Austin med spa", words("w"))}
    assert (
        grade([claimed], other)[claimed.strip()]["status"] == "covered"
    )  # by title and H1
    mention = {f"{HOME}/": page("Home", "Home", words("w") + " we serve Austin")}
    assert grade([claimed], mention)[claimed.strip()]["status"] == "mentioned"


@pytest.mark.parametrize("junk", ["(Texas)", ",", ", TX", "   ", ""])
def test_an_area_with_nothing_left_after_the_state_is_dropped_not_matched_everywhere(
    junk,
):
    pages = {f"{HOME}/tampa/": page("Tampa", "Tampa", words("w"))}
    assert area_pages.grade([junk, "Tampa"], list(pages), pages)[0]["name"] == "Tampa"
    assert len(area_pages.grade([junk], list(pages), pages)) == 0


def test_pages_that_only_carry_the_home_city_in_their_titles_are_not_city_pages():
    """A clinic in Colorado Springs titles every page "... Colorado Springs": the area is
    covered, but that is not a set of service-area pages and no page of them is a hub."""
    city = "Colorado Springs"
    pages = {
        f"{HOME}/": page(f"Glow {city}", f"Glow {city}", words("h")),
        f"{HOME}/services/": page(
            f"Services {city}",
            f"Services {city}",
            words("s"),
        ),
    } | {
        f"{HOME}/botox{i}/": page(
            f"Botox {i} {city}", f"Botox {i} {city}", words(f"b{i}")
        )
        for i in range(4)
    }
    pages[f"{HOME}/services/"] = page(
        f"Services {city}",
        f"Services {city}",
        " ".join(f'<a href="/botox{i}/">b</a>' for i in range(4)),
    )
    s = fresh_sections()
    site_ai.apply(s, {"areas_served": [city]}, pages, list(pages))
    c = s["site"]["cities"]
    assert c["areas"][0]["status"] == "covered"
    assert c["pages_found"] == 0 and c["city_pages"] == []
    assert c["hub_page"] is False


def test_a_city_page_found_only_by_its_title_still_covers_the_area_but_is_not_counted():
    pages = {f"{HOME}/spa/": page("Tampa med spa", "Tampa med spa", words("w"))}
    s = fresh_sections()
    site_ai.apply(s, {"areas_served": ["Tampa"]}, pages, list(pages))
    c = s["site"]["cities"]
    assert c["areas"][0]["status"] == "covered" and c["pages_found"] == 0
