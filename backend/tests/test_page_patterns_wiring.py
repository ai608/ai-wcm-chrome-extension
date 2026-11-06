"""The new address patterns, as the crawler and the area grading actually use them."""

from app.services import area_pages, site_audit, site_crawl

HOME = "https://x.com"


def words(prefix: str, n: int = 320) -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def page(title: str, h1: str, text: str) -> str:
    return f"<html><head><title>{title}</title></head><body><h1>{h1}</h1><main>{text}</main></body></html>"


# ── the crawler's own classes ────────────────────────────────────────────────────────────
def test_classify_knows_the_location_shapes_real_clinics_use():
    city = [
        "/areas-served/bhrt-in-draper-utah/",  # revitalizemedicalsolutions.com
        "/biltmore-office/",  # freshstartaesthetics.com
        "/avere-beauty-locations",  # averebeauty.com
        "/service-area",  # wellnestaesthetics.com
        "/about/locations/lohi/",
    ]
    for path in city:
        assert site_crawl.classify(HOME + path) == "city", path


def test_classify_does_not_call_lookalikes_city_pages():
    for path in (
        "/target-area/face/",
        "/our-dallas-team/",
        "/woodinville-vip/",
        "/locations.kml",
    ):
        assert site_crawl.classify(HOME + path) != "city", path


def test_classify_knows_the_blog_folders_real_clinics_use():
    for path in (
        "/holistic-health-news/a-post",
        "/news-updates/a-post",
        "/posts/a-post",
        "/blog/a-post",
    ):
        assert site_crawl.classify(HOME + path) == "blog_post", path
    assert site_crawl.classify(HOME + "/news-updates/") == "blog_index"


def test_a_category_named_for_a_service_is_a_service_not_an_archive():
    """vivaskinlounge.com keeps /category/botox as a service page; /tag/botox is an archive."""
    urls = [f"{HOME}/category/botox", f"{HOME}/category/news", f"{HOME}/tag/botox"]
    planned = [
        u for group in site_crawl.tiers(urls, HOME + "/").values() for u in group
    ]
    assert f"{HOME}/category/botox" in planned
    assert f"{HOME}/category/news" not in planned and f"{HOME}/tag/botox" not in planned


def test_enrich_counts_only_real_location_pages():
    s = site_audit.analyze(
        "<html><head><title>G</title></head><body><h1>G</h1></body></html>", HOME + "/"
    )
    urls = [
        HOME + "/",
        HOME + "/avere-beauty-locations",
        HOME + "/biltmore-office/",
        HOME + "/scottsdale-office/",
        HOME + "/our-dallas-team/",
        HOME + "/woodinville-vip/",
        HOME + "/target-area/face/",
    ]
    site_crawl.enrich(s, urls, {})
    cities = s["site"]["cities"]
    assert cities["pages_found"] == 3 and cities["hub_page"] is True
    assert sorted(cities["city_pages"]) == sorted(urls[1:4])


# ── naming an area ───────────────────────────────────────────────────────────────────────
def test_an_html_address_still_names_its_city():
    """instituteforintegralhealth.com: every page is /…-colorado-springs.html."""
    url = f"{HOME}/wellness-programs-colorado-springs.html"
    assert area_pages.pages_named("Colorado Springs", [url]) == [url]


def test_a_percent_encoded_space_still_names_its_city():
    url = f"{HOME}/services/botox-cedar%20park/"
    assert area_pages.pages_named("Cedar Park", [url]) == [url]


def test_team_careers_promo_and_proof_pages_never_count_as_a_citys_page():
    others = [
        "/our-dallas-team/",  # lemmonavenueplasticsurgery.com
        "/lemmon-team-frisco/",
        "/aesthetician-careers-in-dallas/",
        "/dallas-vip/",
        "/sip-and-glow-dallas/",
        "/dallas-testimonials/",
        "/contact-us/dallas/",
        "/blog/best-spa-dallas",
        "/privacy-policy-dallas/",
    ]
    own = f"{HOME}/botox-in-dallas-tx/"
    assert area_pages.pages_named("Dallas", [HOME + o for o in others] + [own]) == [own]


def test_grading_ignores_a_team_page_that_names_the_city():
    team = f"{HOME}/our-dallas-team/"
    pages = {team: page("Our Dallas team", "Our Dallas team", words("t"))}
    g = {x["name"]: x for x in area_pages.grade(["Dallas"], list(pages), pages)}[
        "Dallas"
    ]
    assert g["pages"] == [] and g["status"] in ("mentioned", "missing")


def test_dozens_of_service_and_city_pages_in_a_location_folder_do_not_fill_the_service_tiers():
    """revitalizemedicalsolutions.com: 75 pages like /areas-served/bhrt-near-lehi-ut/."""
    area = [f"{HOME}/areas-served/bhrt-near-city{i}-ut/" for i in range(30)]
    area += [
        f"{HOME}/areas-served/testosterone-therapy-in-town{i}-ut/" for i in range(30)
    ]
    services = [
        f"{HOME}/services/male-hormone-optimization/",
        f"{HOME}/services/botox/",
    ]
    tiers = site_crawl.tiers([HOME + "/", *services, *area], HOME + "/")
    service_tiers = [u for t in "ABCD" for u in tiers.get(t, [])]
    assert not set(area) & set(service_tiers)
    assert set(area) <= set(tiers.get("E", []))
    assert set(services) <= set(service_tiers)
