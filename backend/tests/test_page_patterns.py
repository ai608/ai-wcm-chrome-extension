"""Real paths from 59 readable clinic leads (sitemaps read in November 2026), with the answer each
rule must give. If a rule changes, the site it was written from is in the comment."""

import random

import pytest

from app.services import page_patterns as pp

# ── places: pages that ARE area pages by their address ───────────────────────────────────
AREA = [
    "/service-areas/washington-ut/",  # astrahealthandwellness.com
    "/service-areas/st-george-ut/",
    "/service-areas/",
    "/about/locations/boulder/",  # restormedicalspa.com
    "/about/locations/",
    "/about/locations/boulder/testosterone-replacement-therapy-in-boulder/",
    "/locations/west-palm-beach/",  # longevitepalmbeach.com
    "/locations/",
    "/locations",  # mybodytonic: no trailing slash
    "/locations/pottsville",  # botoxbymeesha.com
    "/locations/woodinville/",  # glowlightmedspa.com
    "/location/frisco/",  # renewbeautymedspa.com
    "/location/tx/carrollton",  # livewell-medsolutions.com
    "/areas-served/bhrt-in-draper-utah/",  # revitalizemedicalsolutions.com
    "/areas-served/testosterone-therapy-near-lehi-ut/",
    "/areas-served/menopause-hormone-treatment-near-orem/",
    "/areas-we-serve",  # drseltzerlifestylemedicine.com
    "/service-area",  # wellnestaesthetics.com
    "/avere-beauty-locations",  # averebeauty.com: a flat slug, not a folder
    "/about-us/our-location/",  # rejuvemedspa.com
    "/biltmore-office/",  # freshstartaesthetics.com
    "/scottsdale-office/",
    "/shea-office/",
    "/dexa-scans-near-me-in-sandy-ut",  # a "near me" page
    "/female-hormone-specialist-near-me-in-sandy-utah/",
    "/Locations/Boulder/",  # case
    "/locations/boulder.html",  # extension
]

# ── places: pages that look like area pages but are not ──────────────────────────────────
NOT_AREA = [
    "/target-area/face/",  # hughescenter.net: body areas, not geography
    "/area/chest/",  # renewbeautymedspa.com
    "/area/body/",
    "/locations.kml",  # Yoast local sitemap file (astra, restor, hughes)
    "/location-map/",  # restormedicalspa.com
    "/our-dallas-team/",  # lemmonavenueplasticsurgery.com
    "/lemmon-team-frisco/",
    "/aesthetician-careers-in-dallas/",
    "/woodinville-vip/",  # glowlightmedspa.com: campaigns
    "/woodinville-first-light/",
    "/woodinville-insider/glowlight-woodinville-insider-activated/",
    "/sip-and-glow-woodinville/",
    "/seattle-sun-insider/",
    "/azani-testimonials-lehigh-valley/",  # pittsburghtestosterone.com
    "/azani-downloadable-forms-lehigh-valey/",
    "/contact-pittsburgh-testosterone/",
    "/make-an-appointment/boulder/",  # restormedicalspa.com: booking, not the location page
    "/contact-us/skin-envy-south-austin/",  # skinenvyaustin.com
    "/blog/best-med-spa-dallas",
    "/blog/lip-blushing-austin",
    "/news/pensacolas-dr-v-wellness-on-lab-first-hormone/",  # drvwellnesss.com
    "/cart/",
    "/privacy-policy/",
    "/hello-world/",
    "/",
    "",
]


@pytest.mark.parametrize("path", AREA)
def test_area_pages_by_address(path):
    assert pp.is_area_path(path), path
    assert pp.kind(path) == "area"


@pytest.mark.parametrize("path", NOT_AREA)
def test_pages_that_only_look_like_area_pages(path):
    assert not pp.is_area_path(path), (path, pp.kind(path))


# ── every other kind ─────────────────────────────────────────────────────────────────────
KINDS = {
    "home": ["/", ""],
    "utility": [
        "/hello-world/",
        "/sample-blog",
        "/sample-blog-7",
        "/home-duplicate/",
        "/services-duplicate/",
        "/home-2/",
        "/test/",
        "/html-sitemap/",
        "/site-map/",
        "/sitemap",
        "/404-error/",
        "/coming-soon/",
        "/admin/seo",
        "/dashboard",
        "/mcp",
        "/lander",
        "/auth",
    ],  # evolveatx, mybodytonic, bernardwellness, arizonabeautylab, alchemywellnessatx, glomed
    "shop": [
        "/cart/",
        "/checkout/",
        "/my-account/",
        "/shop/",
        "/store/",
        "/shop-anti-aging-longevity/",
    ],
    "legal": [
        "/privacy-policy/",
        "/terms-and-conditions/",
        "/hipaa-privacy/",
        "/hippa-privacy/",
        "/bernard-wellness-center-do-not-sell-or-share-my-personal-information",
    ],
    "forms": [
        "/medical-release-form/",
        "/resources/consents/botox-consent",
        "/new-patients/pricing/",
        "/resources/pre-post-care/lip-filler",
        "/forms.html",
    ],
    "careers": [
        "/aesthetician-careers-in-dallas/",
        "/therapy-services-careers",
        "/careers/",
        "/jobs/",
    ],
    "team": [
        "/team/jane-doe",
        "/our-team/",
        "/meet-the-team/",
        "/meet-our-providers/",
        "/providers/dr-x/",
        "/provider/x",
        "/team-member/1",
        "/dr-patti-haebe/",
        "/our-medical-team/provider-a/",
        "/about/meet-kasey-netherland/",
        "/our-dallas-team/",
        "/lemmon-team-frisco/",
    ],
    "archive": [
        "/category/news",
        "/tag/botox",
        "/author/sam",
        "/page/2/",
        "/blog/category/tips",
    ],
    "blog_index": [
        "/blog",
        "/blog/",
        "/blogs/",
        "/news-updates/",
        "/posts",
        "/holistic-health-news",
    ],
    "blog_post": [
        "/blog/best-med-spa-dallas",
        "/holistic-health-news/some-post",
        "/news-updates/x",
        "/posts/how-to-x/",
        "/articles/y",
        "/2026/10/some-post/",
        "/blog/wellness-event-in-austin-tx",
    ],
    "promo": [
        "/woodinville-vip/",
        "/sip-and-glow-woodinville/",
        "/special-offers/",
        "/specials/",
        "/referral/",
    ],
    "proof": [
        "/testimonials/",
        "/before-and-after/",
        "/before-after-gallery/botox/",
        "/azani-testimonials-lehigh-valley/",
    ],
    "booking": [
        "/contact-us/",
        "/book-now/",
        "/book-online",
        "/schedule",
        "/make-an-appointment/boulder/",
        "/get-started/aesthetics",
    ],
    "service": [
        "/services/botox/",
        "/service/botox/",
        "/treatments/hydrafacial/",
        "/treatment/hormone-therapy/x/",
        "/procedures/thread-lift/",
        "/med-spa-services/botox",
        "/service-page/adult-adhd-evaluation",
        "/injectables/neuromodulators/botox/",
        "/services/skin/morpheus8/",
        "/services/peptide-therapy/semaglutide/",
    ],
    "service_place": [
        "/botox-in-dallas-tx/",
        "/injectables/botox-in-dallas-tx/",
        "/botox-treatments-in-austin/",
        "/weight-loss-injections-in-austin/",
        "/wellness-injections-in-scottsdale-az/",
        "/botox-for-men-in-dallas-tx/",
        "/chemical-peels-in-dallas-tx-for-men/",
    ],
    # Needs real place names or the page text: no address rule can know these.
    "other": [
        "/cherry",
        "/tampa/",
        "/austin-med-spa",
        "/cheltenham-weight-loss-doctor",
        "/injectables-austin/kybella/",
        "/coolsculpting-austin-tx/",
        "/b12-injections-portland/",
        "/weight-management/glp-1-agonists-are-they-right-for-you/",
        "/about/lissy-wetzel",
        "/integrated-health-services-and-programs-colorado-springs.html",
        "/covid-test/",
        "/services/collections/pottsville/nose-filler/".replace(
            "/services", "/collections"
        ),
        "/botox",
        "/medical-weight-loss",
        "/target-area/face/",
        "/area/chest/",
    ],
}


@pytest.mark.parametrize(
    ("expected", "path"), [(k, p) for k, paths in KINDS.items() for p in paths]
)
def test_kind(expected, path):
    assert pp.kind(path) == expected, (path, pp.kind(path))


# ── places named inside a service slug ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("path", "place"),
    [
        ("/botox-in-dallas-tx/", "dallas"),
        ("/injectables/botox-in-dallas-tx/", "dallas"),
        ("/botox-for-men-in-dallas-tx/", "dallas"),
        ("/chemical-peels-in-dallas-tx-for-men/", "dallas"),
        ("/botox-treatments-in-austin/", "austin"),
        ("/testosterone-hormone-replacement-therapy-in-west-jordan-ut/", "west-jordan"),
        ("/bhrt-near-layton-ut/", "layton"),
        ("/bhrt-in-draper-utah/", "draper"),
        ("/menopause-hormone-treatment-near-orem/", "orem"),
        ("/dexa-scans-near-me-in-sandy-ut", "sandy"),
        ("/female-hormone-specialist-near-me-in-sandy-utah/", "sandy"),
        ("/service/laser-hair-removal-in-dallas/", "dallas"),
        ("/service/botox-in-dallas.html", "dallas"),
    ],
)
def test_place_in_a_service_slug(path, place):
    assert pp.place_candidates(path) == [place]


@pytest.mark.parametrize("path", ["/botox/", "/tampa/", "/austin-med-spa", "/", ""])
def test_no_place_where_the_slug_has_none(path):
    assert pp.place_candidates(path) == []


# ── cleaning ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("https://X.com/Cedar%20Park/About-Us.html", "/cedar-park/about-us"),
        ("https://x.com/", ""),
        ("https://x.com", ""),
        ("/same-day-appointments-Cedar%20Park/", "/same-day-appointments-cedar-park"),
        (
            "/about/lissy-wetzel%20",
            "/about/lissy-wetzel",
        ),  # a stray trailing %20 (botoxbymeesha)
        ("/about//us///", "/about/us"),
        ("/Page.PHP", "/page"),
        ("/a_b/c_d", "/a-b/c-d"),
        ("tampa", "/tampa"),
        ("https://x.com/botox?utm=1#top", "/botox"),
    ],
)
def test_clean_path(raw, clean):
    assert pp.clean_path(raw) == clean


# ── archives ─────────────────────────────────────────────────────────────────────────────
TERMS = ("botox", "filler")


@pytest.mark.parametrize(
    ("path", "archive"),
    [
        ("/category/botox", False),  # vivaskinlounge.com keeps its services here
        ("/category/fillers", False),
        ("/category/news", True),
        ("/category/", True),
        (
            "/blog/category/botox",
            True,
        ),  # under a blog it is an archive whatever it is called
        ("/tag/botox", True),
        ("/author/sam", True),
        ("/page/2/", True),
        ("/wp-content/uploads/a.png", True),
        ("/feed/", True),
        ("/services/botox/", False),
        ("/", False),
    ],
)
def test_archive(path, archive):
    assert pp.is_archive(path, TERMS) is archive


# ── never crashes, always answers ────────────────────────────────────────────────────────
KNOWN = {
    "home",
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
    "area",
    "service_place",
    "service",
    "other",
}


@pytest.mark.parametrize("seed", range(200))
def test_random_addresses(seed):
    rng = random.Random(seed)
    bits = [
        "locations",
        "blog",
        "team",
        "tampa",
        "in",
        "near",
        "me",
        "dallas",
        "tx",
        "-",
        "/",
        "//",
        ".html",
        "%20",
        "%",
        "é",
        "category",
        "cart",
        "BOTOX",
        "2026",
        "10",
        "x" * 80,
        " ",
        "?q=1",
        "#",
        "..",
        "\x00",
    ]
    raw = "".join(rng.choice(bits) for _ in range(rng.randint(0, 14)))
    for url in (raw, "https://x.com/" + raw, "/" + raw):
        assert pp.kind(url) in KNOWN
        assert isinstance(pp.is_area_path(url), bool)
        assert isinstance(pp.place_candidates(url), list)
        assert isinstance(pp.is_archive(url, TERMS), bool)
        once = pp.clean_path(url)
        assert pp.clean_path(once) == once  # cleaning twice changes nothing
