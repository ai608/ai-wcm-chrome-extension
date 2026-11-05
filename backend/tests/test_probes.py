import asyncio
from typing import Any

import httpx
import pytest

from app.core.exceptions import AppError
from app.services import probes

pytestmark = pytest.mark.anyio
G = "https://glow.example"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Web:
    """A fake web for `probes._once`: (method, url) -> (status, headers)."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str]] = []

    async def __call__(
        self, _client: Any, method: str, url: str
    ) -> tuple[int, httpx.Headers]:
        self.calls.append((method, url))
        answer = self.routes.get((method, url)) or self.routes.get(url)
        if answer is None:
            raise AppError(422, "site_unreachable", "no route")
        if isinstance(answer, Exception):
            raise answer
        status, headers = answer
        return status, httpx.Headers(headers)


def use(monkeypatch: pytest.MonkeyPatch, routes: dict[str, Any]) -> Web:
    web = Web(routes)
    monkeypatch.setattr(probes, "_once", web)
    return web


async def head(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as c:
        return await probes.head(c, url)


# ── one URL ───────────────────────────────────────────────────────────────────────────────


async def test_follows_redirects_by_hand_and_reports_hops_headers_and_size(monkeypatch):
    use(
        monkeypatch,
        {
            f"{G}/a": (301, {"location": "/b"}),
            f"{G}/b": (302, {"location": f"{G}/c"}),
            f"{G}/c": (
                200,
                {
                    "x-robots-tag": "noindex",
                    "content-length": "1234",
                    "content-type": "text/html",
                },
            ),
        },
    )
    assert await head(f"{G}/a") == {
        "status": 200,
        "final": f"{G}/c",
        "hops": 2,
        "x_robots": "noindex",
        "length": 1234,
        "type": "text/html",
    }


async def test_a_head_that_says_missing_is_checked_again_with_get_before_it_counts(
    monkeypatch,
):
    web = use(
        monkeypatch, {("HEAD", f"{G}/p"): (404, {}), ("GET", f"{G}/p"): (200, {})}
    )
    assert (await head(f"{G}/p"))["status"] == 200  # the server just dislikes HEAD
    assert [m for m, _ in web.calls] == ["HEAD", "GET"]
    use(monkeypatch, {("HEAD", f"{G}/q"): (404, {}), ("GET", f"{G}/q"): (404, {})})
    assert (await head(f"{G}/q"))["status"] == 404  # really missing


async def test_a_loop_a_refused_address_and_a_network_error_are_unknown_not_broken(
    monkeypatch,
):
    use(monkeypatch, {f"{G}/x": (301, {"location": f"{G}/x"})})
    looped = await head(f"{G}/x")
    assert looped["status"] is None and looped["hops"] == probes.MAX_HOPS + 1
    use(monkeypatch, {"http://internal.local/": AppError(422, "url_not_allowed", "no")})
    assert (await head("http://internal.local/"))["status"] is None
    use(monkeypatch, {f"{G}/e": httpx.ConnectError("down")})
    assert (await head(f"{G}/e"))["status"] is None


async def test_a_real_request_is_never_sent_to_an_internal_address():
    # not monkeypatched: the real guard (normalize_url / _public_ip) must refuse these
    for url in (
        "http://localhost/",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
    ):
        assert (await head(url))["status"] is None


# ── what to check ─────────────────────────────────────────────────────────────────────────


PAGES = {
    f"{G}/": (
        '<a href="/services/botox">B</a><a href="/about">A</a><a href="#top">t</a>'
        '<a href="mailto:a@b.c">m</a><a href="tel:555">t</a><a href="/logo.png">i</a>'
        '<a href="https://other.example/x">ext</a><a href="/contact">c</a>'
    ),
    f"{G}/services/botox": '<a href="/contact">c</a><a href="/blog/post-1">p</a><a href="/">h</a>',
}


def test_link_candidates_skip_read_pages_junk_images_and_other_sites_and_rank_by_how_often_linked():
    got = probes.link_candidates(PAGES, f"{G}/")
    urls = [u for u, _ in got]
    assert urls[0] == f"{G}/contact"  # linked from two pages: first
    assert set(urls) == {f"{G}/about", f"{G}/contact", f"{G}/blog/post-1"}
    assert (
        dict(got)[f"{G}/blog/post-1"] == f"{G}/services/botox"
    )  # a page that links to it
    assert len(probes.link_candidates(PAGES, f"{G}/", limit=1)) == 1


def test_host_variants_cover_http_https_www_and_bare():
    assert probes._host_variants("https://www.glow.example/x") == [
        "http://glow.example/",
        "http://www.glow.example/",
        "https://glow.example/",
        "https://www.glow.example/",
    ]


# ── the whole batch ───────────────────────────────────────────────────────────────────────


HOME = '<html><body><img src="/big.jpg"><img src="data:image/gif;base64,xx"><img src="/a.png"><a href="/gone">g</a></body></html>'


async def test_run_checks_hosts_links_images_and_the_favicon_when_there_is_no_icon_tag(
    monkeypatch,
):
    routes: dict[str, Any] = {
        "http://glow.example/": (301, {"location": "https://glow.example/"}),
        "http://www.glow.example/": (301, {"location": "https://glow.example/"}),
        "https://glow.example/": (200, {}),
        "https://www.glow.example/": (301, {"location": "https://glow.example/"}),
        f"{G}/gone": (404, {}),
        f"{G}/big.jpg": (200, {"content-length": "900000"}),
        f"{G}/a.png": (200, {"content-length": "1000"}),
        f"{G}/favicon.ico": (404, {}),
    }
    routes[("GET", f"{G}/gone")] = (404, {})
    routes[("GET", f"{G}/favicon.ico")] = (404, {})
    web = use(monkeypatch, routes)
    out = await probes.run(home=f"{G}/", home_html=HOME, pages={f"{G}/": HOME})
    assert {h["url"]: h["final"] for h in out["hosts"]} == {
        "http://glow.example/": "https://glow.example/",
        "http://www.glow.example/": "https://glow.example/",
        "https://glow.example/": "https://glow.example/",
        "https://www.glow.example/": "https://glow.example/",
    }
    assert [(l["url"], l["status"]) for l in out["links"]] == [(f"{G}/gone", 404)]
    assert {i["url"]: i["length"] for i in out["images"]} == {
        f"{G}/big.jpg": 900000,
        f"{G}/a.png": 1000,
    }
    assert (
        out["favicon"]["status"] == 404
        and out["timed_out"] == 0
        and out["checked"] == 8  # 4 hosts, 1 link, 2 images, the favicon
    )
    assert not any("data:" in u for _, u in web.calls)


async def test_the_favicon_is_not_probed_when_the_page_has_an_icon_tag(monkeypatch):
    web = use(
        monkeypatch, {}
    )  # everything is "unreachable": statuses are None, nothing is claimed
    html = '<html><head><link rel="shortcut icon" href="/f.png"></head><body></body></html>'
    out = await probes.run(home=f"{G}/", home_html=html, pages={f"{G}/": html})
    assert out["favicon"] is None and all(h["status"] is None for h in out["hosts"])
    assert not any(u.endswith("favicon.ico") for _, u in web.calls)


async def test_requests_that_outlast_the_budget_are_dropped_and_counted(monkeypatch):
    async def hang(*_a: Any) -> tuple[int, httpx.Headers]:
        await asyncio.sleep(10)
        return 200, httpx.Headers()

    monkeypatch.setattr(probes, "_once", hang)
    monkeypatch.setattr(probes, "BUDGET_S", 0.05)
    out = await probes.run(home=f"{G}/", home_html=HOME, pages={f"{G}/": HOME})
    assert out["checked"] == 0 and out["timed_out"] > 0 and out["hosts"] == []


async def test_only_a_few_requests_run_at_once(monkeypatch):
    running = peak = 0

    async def slow(*_a: Any) -> tuple[int, httpx.Headers]:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return 200, httpx.Headers()

    monkeypatch.setattr(probes, "_once", slow)
    pages = {f"{G}/": "".join(f'<a href="/p{i}">x</a>' for i in range(15))}
    await probes.run(home=f"{G}/", home_html=pages[f"{G}/"], pages=pages)
    assert 1 < peak <= probes.CONCURRENCY
