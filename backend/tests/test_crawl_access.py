import pytest

from app.core.exceptions import AppError
from app.services import crawl_access, onpage, site_audit, site_crawl

G = "https://glow.example"
URLSET = "<urlset>{}</urlset>"


def loc(*paths):
    return "".join(f"<url><loc>{G}{p}</loc></url>" for p in paths)


def page(url, noindex=False, canonical="ok"):
    return {"url": url, "noindex": noindex, "canonical": {"status": canonical}}


def raw(robots="", sitemap=None, state="ok"):
    groups, listed = crawl_access.parse_robots(robots)
    urls = sitemap or []
    return {
        "state": state,
        "groups": groups,
        "declared": bool(listed),
        "files": [],
        "urls": [f"{G}{p}" for p in urls],
        "truncated": False,
    }


def keys(found):
    return {k for k, _ in found}


def test_the_longest_matching_rule_wins_and_allow_wins_a_tie():
    rules = [
        (False, "/private/"),
        (True, "/private/open/"),
        (False, "/*.pdf$"),
        (True, "/a"),
        (False, "/a"),
    ]
    assert crawl_access.blocked(rules, "/private/x")
    assert not crawl_access.blocked(rules, "/private/open/x")
    assert crawl_access.blocked(rules, "/files/menu.pdf")
    assert not crawl_access.blocked(rules, "/files/menu.pdf?x=1")
    assert not crawl_access.blocked(rules, "/a")
    assert not crawl_access.blocked(rules, "/other")


def test_robots_groups_share_rules_and_googlebot_beats_the_star_group():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: bingbot\nUser-agent: googlebot\nDisallow: /tmp # note\nSitemap: https://glow.example/s.xml\n"
    groups, listed = crawl_access.parse_robots(text)
    assert listed == ["https://glow.example/s.xml"]
    assert crawl_access.rules_for(groups, "googlebot") == [(False, "/tmp")]
    assert crawl_access.rules_for(groups, "other") == [(False, "/")]


def test_a_site_wide_block_is_critical_and_page_blocks_are_counted():
    core = [G, f"{G}/botox", f"{G}/fillers"]
    _, found = crawl_access.judge(raw("User-agent: *\nDisallow: /\n"), G, "", core, [])
    assert "robots_blocks_site" in keys(found)
    _, found = crawl_access.judge(
        raw("User-agent: *\nDisallow: /botox\n", ["/"]), G, "", core, []
    )
    assert ("robots_blocks_pages", "1") in found


def test_blocked_style_and_script_files_of_the_home_page_are_found():
    html = '<link rel="stylesheet" href="/wp-content/a.css"><script src="/wp-includes/j.js"></script><script src="https://cdn.x/y.js"></script>'
    info, found = crawl_access.judge(
        raw("User-agent: *\nDisallow: /wp-content/\n", ["/"]), G, html, [G], []
    )
    assert ("robots_blocks_assets", "1") in found
    assert info["robots"]["blocked_assets"] == 1


def test_an_unreachable_robots_file_is_flagged_and_a_missing_one_is_fine():
    assert "robots_unreachable" in keys(
        crawl_access.judge(raw(state="error"), G, "", [G], [])[1]
    )
    assert "robots_unreachable" not in keys(
        crawl_access.judge(raw(state="missing"), G, "", [G], [])[1]
    )


def test_no_sitemap_and_a_broken_listed_sitemap_are_told_apart():
    assert keys(crawl_access.judge(raw(), G, "", [G], [])[1]) == {"sitemap_missing"}
    listed = raw("Sitemap: https://glow.example/s.xml\n")
    assert keys(crawl_access.judge(listed, G, "", [G], [])[1]) == {"sitemap_broken"}


def test_sitemap_gaps_noindex_pages_and_blocked_urls_are_found():
    core = [G, f"{G}/botox", f"{G}/fillers"]
    text = "User-agent: *\nDisallow: /fillers\n"
    _info, found = crawl_access.judge(
        raw(text, ["/", "/botox", "/fillers", "/old"]),
        G,
        "",
        core,
        [page(f"{G}/botox", noindex=True), page(f"{G}/old", canonical="other_page")],
    )
    assert keys(found) == {
        "sitemap_not_in_robots",
        "sitemap_bad_urls",
        "sitemap_blocked",
        "robots_blocks_pages",
    }
    assert ("sitemap_bad_urls", "2") in found
    _, found = crawl_access.judge(raw(text, ["/"]), G, "", core, [])
    assert ("sitemap_missing_pages", "2") in found


def test_a_complete_sitemap_with_the_robots_line_has_no_issue():
    text = "User-agent: *\nDisallow: /wp-admin/\nSitemap: https://glow.example/sitemap.xml\n"
    core = [G, f"{G}/botox"]
    info, found = crawl_access.judge(
        raw(text, ["/", "/botox/"]), G, "", core, [page(G)]
    )
    assert found == []
    assert info["sitemap"]["urls"] == 2


@pytest.fixture
def web(monkeypatch):
    pages: dict[str, str | None] = {}

    async def fake(url, accept=None):
        body = pages.get(url)
        if body is None:
            raise AppError(422, "site_unreachable", "x")
        if body == "5xx":
            raise site_audit.TransientFetchError("x")
        return body, url

    monkeypatch.setattr(site_audit, "fetch_html", fake)
    return pages


@pytest.mark.anyio
async def test_load_follows_the_robots_line_and_a_sitemap_index(web):
    web[f"{G}/robots.txt"] = (
        "Sitemap: https://glow.example/index.xml\nSitemap: https://other.example/x.xml"
    )
    web[f"{G}/index.xml"] = (
        f"<sitemapindex><sitemap><loc>{G}/a.xml</loc></sitemap><sitemap><loc>{G}/b.xml</loc></sitemap></sitemapindex>"
    )
    web[f"{G}/a.xml"] = URLSET.format(loc("/", "/botox"))
    web[f"{G}/b.xml"] = "not xml"
    got = await crawl_access.load(G)
    assert got["declared"] and got["state"] == "ok"
    assert got["urls"] == [f"{G}/", f"{G}/botox"]
    assert [f["state"] for f in got["files"]] == ["ok", "ok", "invalid"]


@pytest.mark.anyio
async def test_load_guesses_the_sitemap_and_stops_at_the_first_that_works(web):
    web[f"{G}/sitemap.xml"] = URLSET.format(loc("/"))
    web[f"{G}/wp-sitemap.xml"] = URLSET.format(loc("/never"))
    web[f"{G}/robots.txt"] = "5xx"
    got = await crawl_access.load(G)
    assert got["state"] == "error" and not got["declared"]
    assert got["urls"] == [f"{G}/"]
    assert [f["url"] for f in got["files"]] == [f"{G}/sitemap.xml"]


def test_run_adds_the_access_issues_to_the_score():
    sections = {
        "on_page": {"links": {}, "images": {}},
        "schema": {},
        "business": {"nap": {}},
        "site": {"services": {"clusters": []}},
    }
    html = "<html><head><title>Glow Clinic Home | Austin</title></head><body><h1>Glow</h1></body></html>"
    menu = site_crawl.Menu({}, {}, {})
    access = raw("User-agent: *\nDisallow: /\n")
    onpage.run(sections, G, {G: html}, [G], menu, access)
    assert sections["on_page"]["access"]["robots"]["blocks_site"]
    assert any(
        i["key"] == "robots_blocks_site" for i in sections["on_page"]["site_issues"]
    )
    assert sections["on_page"]["summary"]["critical"] >= 1
