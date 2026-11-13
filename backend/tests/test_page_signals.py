import pytest

from app.services import area_pages, page_signals

G = "https://glow.example"


def page(title: str = "", h1: str = "", body: str = "", head: str = "") -> str:
    return (
        f"<html><head><title>{title}</title>{head}</head>"
        f"<body><h1>{h1}</h1><p>{body}</p></body></html>"
    )


@pytest.mark.parametrize(
    ("url", "html", "reason"),
    [
        (
            f"{G}/product-page/i-m-a-product-7",
            None,
            "demo product",
        ),  # Wix demo, not read
        (f"{G}/about-us-test", page("About"), "Test, copy"),
        (f"{G}/copy-of-stephanie-mcelroy", page("Stephanie"), "Test, copy"),
        (f"{G}/pages-not-being-used/hormones", None, "Test, copy"),
        (
            f"{G}/newnan",
            page("Page not found – Clinic", "The page can’t be found."),
            "not found",
        ),
        (f"{G}/x", page("I’m a product | Shop"), "placeholder title"),
    ],
)
def test_pages_that_should_not_be_live(url, html, reason):
    assert reason in (page_signals.unfinished(url, html) or "")


@pytest.mark.parametrize(
    "url",
    [f"{G}/testimonials", f"{G}/botox-testing-results", f"{G}/services/botox"],
)
def test_real_pages_are_not_unfinished(url):
    assert page_signals.unfinished(url, page("Botox | Glow", "Botox")) is None


def test_leftover_builder_text_is_a_finding_but_the_page_is_real():
    html = page(
        "Botox",
        "Botox",
        "This is some text inside of a div block. Botox lasts 3 months.",
    )
    assert page_signals.unfinished(f"{G}/botox", html) is None
    assert "div block" in page_signals.placeholder_text(html)


def test_a_post_is_known_by_blogposting_or_a_byline_not_by_og_article():
    seo_plugin_page = page(
        "Botox",
        head='<meta property="og:type" content="article">'
        '<meta property="article:published_time" content="2024-01-01">',
    )
    assert not page_signals.is_post(seo_plugin_page)  # SEO plugins tag service pages so
    assert page_signals.is_post(
        page(head='<script type="application/ld+json">{"@type":"BlogPosting"}</script>')
    )
    assert page_signals.is_post(
        '<html><body><span class="byline">By Ann</span></body></html>'
    )


@pytest.mark.parametrize(
    ("title", "h1", "person"),
    [
        ("Dr. Justin Grace | Paramount", "", True),
        ("Laquita Martinez, MD, FACOG: Alpharetta", "", True),
        ("Margeaux King | Paramount", "The Team", True),
        ("Botox | Glow", "Botox", False),
        ("Hormone Therapy | Dr. Lee's Clinic", "Hormone Therapy", False),
    ],
)
def test_a_persons_page_by_title_or_team_heading(title, h1, person):
    assert page_signals.is_person(page(title, h1)) is person


def test_trust_pages_by_what_they_call_themselves_and_never_shop_or_careers():
    pages = {
        f"{G}/frequently-asked-questions": page(
            "FAQ | Clinic", "Frequently asked questions"
        ),
        f"{G}/who-is-taking-care-of-you": page(
            "Meet Our Team | Clinic", "The people behind"
        ),
        f"{G}/services": page("Services | Clinic", "About Services"),
        f"{G}/about": page("About Us | Clinic", "Our story"),
        f"{G}/join-our-team": page("Join Our Team | Clinic", "Careers"),
    }
    urls = [
        *pages,
        f"{G}/shop/p/a-team-duo-kit",
        f"{G}/your-privacy",
        f"{G}/category/providers",
        f"{G}/lets-talk-about-skin",
    ]
    got = page_signals.trust_pages(urls, pages)
    assert got["faq_page"] == f"{G}/frequently-asked-questions"
    assert got["team_page"] == f"{G}/who-is-taking-care-of-you"
    assert got["about_page"] == f"{G}/about"  # not "About Services"
    assert got["privacy_policy"] == f"{G}/your-privacy"


def test_the_clinics_own_town_in_service_addresses_makes_no_city_page():
    urls = [
        f"{G}/{s}-savannah"
        for s in ["botox", "dysport", "jeuveau", "fillers", "kybella", "lip-flip"]
    ]
    urls += [f"{G}/savannah-ga", f"{G}/pooler", f"{G}/botox-pooler", f"{G}/about"]
    own = area_pages.own_places(["Savannah", "Pooler"], urls, [])
    assert own == {"savannah"}  # in most addresses: the clinic's own town
    assert area_pages.pages_named("Savannah", urls, own=True) == [f"{G}/savannah-ga"]
    assert area_pages.pages_named("Pooler", urls) == [
        f"{G}/pooler",
        f"{G}/botox-pooler",
    ]
    assert area_pages.own_places([], [], ["Colorado Springs"]) == {"colorado-springs"}


@pytest.mark.parametrize(
    ("url", "html", "reason"),
    [
        (
            f"{G}/wp-includes/js",
            page("Index of /wp-includes/js", "Index of /wp-includes/js"),
            "directory listing",
        ),
        (f"{G}/sample-post-2", None, "Theme demo"),
        (f"{G}/hello-world", None, "Theme demo"),
    ],
)
def test_folder_listings_and_theme_demo_posts_are_flagged(url, html, reason):
    assert reason in (page_signals.unfinished(url, html) or "")


def test_the_clinics_town_from_a_suffix_most_titles_share():
    titles = [
        "Botox | Plano, TX | Metamorph",
        "Fillers | Plano, TX | Metamorph",
        "Contact | Plano, TX | Metamorph",
        "Blog: Tips for Dallas, TX brides",
    ]
    pages = {f"{G}/{i}": page(t) for i, t in enumerate(titles)}
    assert page_signals.title_town(pages) == "Plano"
    assert page_signals.title_town({f"{G}/a": page("Botox in Dallas, TX")}) is None


def test_a_crew_page_is_the_team_page_and_the_home_page_is_never_a_trust_page():
    pages = {
        f"{G}/": page("Glow Aesthetics", "About"),
        f"{G}/the-medspa-crew": page("The MedSpa Crew | Glow", "The MedSpa Crew"),
    }
    got = page_signals.trust_pages(list(pages), pages)
    assert got.get("team_page") == f"{G}/the-medspa-crew" and "about_page" not in got


@pytest.mark.parametrize(
    "hidden",
    [
        '<div class="hidden">This is some text inside of a div block.</div>',  # Webflow / Viva
        "<div hidden>Lorem ipsum dolor</div>",
        '<div aria-hidden="true">Lorem ipsum dolor</div>',
        '<div style="display: none">Lorem ipsum dolor</div>',
        '<div class="w-condition-invisible"><p>Lorem ipsum dolor</p></div>',
        '<style>.old-promo{display:none}</style><div class="card old-promo">Lorem ipsum</div>',
        "<template><p>Lorem ipsum dolor</p></template>",
    ],
)
def test_placeholder_text_a_visitor_cannot_see_is_not_reported(hidden):
    html = f"<html><body><h1>Botox</h1><p>Smooth lines fast.</p>{hidden}</body></html>"
    assert page_signals.placeholder_text(html) is None


def test_visible_placeholder_text_is_reported():
    html = "<html><body><div class='card'><h3>Title Goes Here</h3><p>Lorem ipsum dolor sit</p></div></body></html>"
    assert "lorem ipsum" in page_signals.placeholder_text(html)


@pytest.mark.parametrize(
    ("path", "test_page"),
    [
        ("/test", True),
        ("/product/test", True),
        ("/about-us-test", True),
        ("/location/test-location/", True),
        (
            "/bioidentical-hormones-test-in-utah",
            False,
        ),  # an article about hormone testing
        ("/the-pinnacle-of-mens-health-our-comprehensive-male-performance-test", False),
        ("/testimonials", False),
        ("/a1c-test", False),
    ],
)
def test_a_test_page_is_one_named_as_such_not_a_page_about_a_medical_test(
    path, test_page
):
    got = page_signals.unfinished(f"{G}{path}", None)
    assert (got == "Test, copy or unused page") is test_page


def test_elementor_text_hidden_on_every_device_is_not_reported_but_on_one_device_it_is():
    every = '<div class="elementor-hidden-desktop elementor-hidden-tablet elementor-hidden-mobile">'
    one = '<div class="elementor-hidden-mobile elementor-invisible">'
    body = "<h3>Sample Title</h3><p>Lorem ipsum dolor sit</p></div>"
    assert (
        page_signals.placeholder_text(f"<html><body>{every}{body}</body></html>")
        is None
    )
    assert page_signals.placeholder_text(f"<html><body>{one}{body}</body></html>")
