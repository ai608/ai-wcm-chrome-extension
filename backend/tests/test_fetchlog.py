import asyncio
from typing import Any

import httpx
import pytest

from app.core.exceptions import AppError
from app.services import fetchlog, site_audit

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def serve(
    monkeypatch: pytest.MonkeyPatch, routes: dict[str, httpx.Response]
) -> list[str]:
    """Run the real `_fetch_once` against a fake web: every host is public, answers come from
    `routes` (keyed by the Host header + path)."""
    asked: list[str] = []

    async def public(_host: str, _port: int) -> str:
        return "93.184.216.34"

    def handler(req: httpx.Request) -> httpx.Response:
        key = req.headers["host"] + req.url.path
        asked.append(key)
        return routes[key]

    real = httpx.AsyncClient
    monkeypatch.setattr(site_audit, "_public_ip", public)
    monkeypatch.setattr(
        site_audit.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    return asked


def html(text: str = "<html><title>x</title></html>", **headers: str) -> httpx.Response:
    return httpx.Response(
        200, text=text, headers={"content-type": "text/html", **headers}
    )


async def test_records_where_a_page_ended_up_how_many_redirects_it_took_and_the_header(
    monkeypatch,
):
    serve(
        monkeypatch,
        {
            "glow.example/botox": httpx.Response(301, headers={"location": "/botox/"}),
            "glow.example/botox/": httpx.Response(
                302, headers={"location": "https://glow.example/botox-new/"}
            ),
            "glow.example/botox-new/": html(**{"x-robots-tag": "noindex, nofollow"}),
        },
    )
    log = fetchlog.bind()
    await site_audit._fetch_once("https://glow.example/botox")
    assert log["https://glow.example/botox"] == {
        "final": "https://glow.example/botox-new/",
        "hops": 2,
        "status": 200,
        "x_robots": "noindex, nofollow",
    }


async def test_records_a_missing_page_and_still_raises(monkeypatch):
    serve(monkeypatch, {"glow.example/gone": httpx.Response(404)})
    log = fetchlog.bind()
    with pytest.raises(AppError):
        await site_audit._fetch_once("https://glow.example/gone")
    assert log["https://glow.example/gone"] == {
        "final": "https://glow.example/gone",
        "hops": 0,
        "status": 404,
    }


async def test_a_busy_server_is_not_recorded_as_a_missing_page(monkeypatch):
    serve(monkeypatch, {"glow.example/busy": httpx.Response(503)})
    log = fetchlog.bind()
    with pytest.raises(site_audit.TransientFetchError):
        await site_audit._fetch_once("https://glow.example/busy")
    assert log == {}  # a passing failure says nothing about the page


async def test_with_no_audit_bound_nothing_is_kept_and_nothing_breaks(monkeypatch):
    serve(monkeypatch, {"glow.example/": html()})
    await site_audit._fetch_once("https://glow.example/")
    assert fetchlog.snapshot() == {}
    fetchlog.record("https://x/", final="https://x/", hops=0)  # no-op


async def test_two_audits_keep_separate_logs():
    async def audit(name: str) -> dict[str, Any]:
        fetchlog.bind()
        await asyncio.sleep(0.01)
        fetchlog.record(f"https://{name}/", hops=0)
        await asyncio.sleep(0.01)
        return fetchlog.snapshot()

    a, b = await asyncio.gather(
        asyncio.create_task(audit("a.example")), asyncio.create_task(audit("b.example"))
    )
    assert list(a) == ["https://a.example/"] and list(b) == ["https://b.example/"]


async def test_the_log_is_bounded():
    async def audit() -> int:
        fetchlog.bind()
        for i in range(fetchlog.MAX_ENTRIES + 50):
            fetchlog.record(f"https://x/{i}", hops=0)
        fetchlog.record("https://x/0", hops=9)  # an existing entry may still be updated
        return len(fetchlog.snapshot())

    assert await asyncio.create_task(audit()) == fetchlog.MAX_ENTRIES


async def test_robots_and_sitemap_reads_are_not_page_reads_and_leave_no_entry(
    monkeypatch,
):
    """A sitemap that redirects is the site's business, not an internal link that redirects."""
    serve(
        monkeypatch,
        {
            "glow.example/sitemap.xml": httpx.Response(
                301, headers={"location": "/sitemap_index.xml"}
            ),
            "glow.example/sitemap_index.xml": httpx.Response(
                200, text="<urlset/>", headers={"content-type": "application/xml"}
            ),
            "glow.example/missing.xml": httpx.Response(404),
        },
    )
    log = fetchlog.bind()
    await site_audit._fetch_once(
        "https://glow.example/sitemap.xml", accept=("application/xml", "text/xml")
    )
    with pytest.raises(AppError):
        await site_audit._fetch_once(
            "https://glow.example/missing.xml", accept=("application/xml",)
        )
    assert log == {}
