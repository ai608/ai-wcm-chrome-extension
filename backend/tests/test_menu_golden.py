from pathlib import Path

import pytest

from app.services import site_crawl

FIXTURES = Path(__file__).parent / "fixtures"
SITES = {
    "elite": "https://elitehealthcolorado.com/",
    "institute": "https://instituteforintegralhealth.com/",
    "astra": "https://astrahealthandwellness.com/",
}


def menu_of(name):
    html = (FIXTURES / f"menu_{name}.html").read_text()
    return site_crawl.nav_links(html, SITES[name]), SITES[name]


def kinds(name):
    menu, home = menu_of(name)
    return {
        u.removeprefix(home.rstrip("/")): site_crawl.classify(u, menu) for u in menu.top
    }


def test_elite_menu_has_two_hubs_and_twelve_services_under_them():
    menu, _ = menu_of("elite")
    assert set(menu.parents.values()) == {
        "Internal Optimization",
        "External Optimization",
    }
    assert len(menu.children) == 12
    k = kinds("elite")
    assert k["/peptide-therapy/"] == "menu_child" and k["/iv-therapy/"] == "service"
    assert k["/internal-optimization/"] == "hub" and k["/about/"] == "trust"


def test_institute_menu_finds_seven_services_and_the_cost_page_by_its_text():
    menu, _ = menu_of("institute")
    assert len(menu.children) == 9 and menu.parents.keys() >= {
        "https://instituteforintegralhealth.com/integrated-health-services-and-programs-colorado-springs.html"
    }
    k = kinds("institute")
    services = [p for p, c in k.items() if c in ("menu_child", "service")]
    assert len(services) == 7
    assert k["/integrative-health-programs-cost-colorado-springs.html"] == "trust"
    assert k["/integrative-health-specialist-colorado-springs.html"] == "trust"
    assert k["/cutv-interview-part-1.html"] == "other"


def test_astra_menu_keeps_the_first_name_of_a_page_linked_twice():
    menu, home = menu_of("astra")
    assert menu.top[f"{home}menopause/"] == "menopause treatment"
    assert menu.top[f"{home}medical-spa/"] == "med spa"
    assert "#" not in "".join(menu.parents)
    k = kinds("astra")
    assert k["/medical-spa/"] == "hub" and k["/menopause/"] == "menu_child"
    assert k["/blog/"] == "blog_index"


@pytest.mark.parametrize("name", SITES)
def test_every_service_hub_and_trust_page_in_the_menu_is_read(name):
    menu, home = menu_of(name)
    chosen, _, _ = site_crawl.plan([home, *menu.top], home, menu)
    wanted = {
        u
        for u in menu.top
        if site_crawl.classify(u, menu) in ("service", "menu_child", "hub", "trust")
    }
    assert wanted and wanted <= set(chosen)
