import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
import pytest

from app.api.v1 import ext, research
from app.core.config import settings
from app.core.dependencies import require_extension_access
from app.core.exceptions import AppError
from app.main import app
from app.models.user import UserProfile
from app.repositories.audit_repository import COLUMNS
from app.services import (
    ai_report,
    ai_runs,
    ai_visibility,
    audit_runner,
    local_competitors,
    probes,
    site_audit,
)

pytestmark = pytest.mark.anyio

HTML = """<html lang="en"><head><title>Glow Med Spa Austin | Botox and Fillers</title>
<meta name="viewport" content="width=device-width"></head><body><h1>Glow Med Spa</h1>
<a href="/services/botox">Botox</a><a href="tel:+15125550000">Call</a></body></html>"""


class Row(dict[str, Any]):
    pass


class FakeRepo:
    def __init__(self) -> None:
        self.rows: dict[str, Row] = {}
        self.runs: dict[str, dict[str, Any]] = {}

    async def create(
        self, user_id: str, url: str, domain: str, state: dict[str, str]
    ) -> Row:
        row = Row(
            id=uuid.uuid4(),
            url=url,
            domain=domain,
            status="queued",
            error=None,
            section_state=json.dumps(state),
            trace="[]",
            **{c: None for c in COLUMNS.values()},
            created_at=datetime.now(UTC),
            finished_at=None,
        )
        self.rows[str(row["id"])] = row
        return row

    async def get(self, audit_id: str) -> Row | None:
        return self.rows.get(audit_id)

    async def latest(self, domain: str, fresh_only: bool = False) -> Row | None:
        hits = [
            r
            for r in self.rows.values()
            if r["domain"] == domain and r["status"] != "failed"
        ]
        return hits[-1] if hits else None

    async def add_trace(self, audit_id: str, event: dict[str, Any]) -> None:
        r = self.rows[audit_id]
        r["trace"] = json.dumps([*json.loads(r["trace"]), event])

    async def update(
        self,
        audit_id: str,
        *,
        status: str | None = None,
        error: str | None = None,
        state: dict[str, str] | None = None,
        sections: dict[str, Any] | None = None,
        finished: bool = False,
    ) -> None:
        r = self.rows[audit_id]
        r["status"] = status or r["status"]
        r["error"] = error or r["error"]
        r["section_state"] = json.dumps(
            {**json.loads(r["section_state"]), **(state or {})}
        )
        for k, v in (sections or {}).items():
            r[COLUMNS[k]] = json.dumps(v)
        if finished:
            r["finished_at"] = datetime.now(UTC)

    # AI visibility runs: same contract as AuditRepository, kept as the row's `ai_run`.
    spent = 0

    async def create_ai_run(
        self, audit_id: str, user_id: str, config: dict[str, Any]
    ) -> str | None:
        if any(
            r["audit_id"] == audit_id and r["state"] == "running"
            for r in self.runs.values()
        ):
            return None
        run_id = str(uuid.uuid4())
        self.runs[run_id] = {
            "audit_id": audit_id,
            "state": "running",
            "data": None,
            "error": None,
            "kind": "full",
            "config": config,
        }
        self._sync(run_id)
        return run_id

    async def get_ai_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        return {
            "id": run_id,
            "audit_id": run["audit_id"],
            "kind": run["kind"],
            "status": run["state"],
            "config": run["config"],
            "created_at": datetime.now(UTC),
        }

    async def running_full_runs(self) -> list[str]:
        return [
            i
            for i, r in self.runs.items()
            if r["kind"] == "full" and r["state"] == "running"
        ]

    answers_page: ClassVar[
        list[dict[str, Any]]
    ] = []  # tests replace it on the instance

    async def ai_answer_page(self, run_id: str, **kw: Any) -> list[dict[str, Any]]:
        self.last_page = kw
        return self.answers_page

    async def save_ai_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        data: dict[str, Any] | None = None,
        error: str | None = None,
        cost_micro: int | None = None,
        tokens: int | None = None,
        finished: bool = False,
    ) -> None:
        run = self.runs[run_id]
        run["state"] = status or run["state"]
        run["data"] = data if data is not None else run["data"]
        run["error"] = error or run["error"]
        self._sync(run_id)

    async def ai_spend_micro(self, user_id: str) -> int:
        return self.spent

    async def set_audit_spend(
        self, audit_id: str, cost_micro: int, tokens: int
    ) -> None:
        self.rows[audit_id]["ai_cost_micro"] = cost_micro
        self.rows[audit_id]["ai_tokens"] = tokens

    async def ai_spend_summary(self) -> dict[str, Any]:
        rows = self.rows.values()
        audits = sum(int(r.get("ai_cost_micro", 0)) for r in rows)
        return {
            "total": audits + 7_000,
            "day": audits,
            "week": audits + 2_000,
            "month": audits + 7_000,
            "audits": audits,
            "ai_visibility": 7_000,
            "users": 2,
        }

    def _sync(self, run_id: str) -> None:
        run = self.runs[run_id]
        self.rows[run["audit_id"]]["ai_run"] = json.dumps(
            {
                "state": run["state"],
                "data": run["data"],
                "error": run["error"],
                "ran_at": datetime.now(UTC).isoformat(),
            }
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(research, "get_audit_repo", lambda _request: repo)
    monkeypatch.setattr(ext, "get_audit_repo", lambda _request: repo)  # Settings usage

    async def fake_fetch(url: str, accept=None) -> tuple[str, str]:
        if "down" in url:
            raise AppError(422, "site_unreachable", "Website could not be fetched")
        return HTML, url

    monkeypatch.setattr(site_audit, "fetch_html", fake_fetch)
    now = datetime.now(UTC)
    user = UserProfile(
        id=str(uuid.uuid4()),
        email="sdr@example.com",
        full_name="Sam Rep",
        avatar_url=None,
        role="user",
        is_active=True,
        admin_id=None,
        created_at=now,
        updated_at=now,
    )
    app.dependency_overrides[require_extension_access] = lambda: user
    # The routes read the app's shared HTTP client; without this the file only passes when
    # another test file has already set it. Every provider call is faked, so it is never used.
    shared = httpx.AsyncClient()
    monkeypatch.setattr(app.state, "http_client", shared, raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as c:
        c.repo = repo  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()
    await shared.aclose()


async def settle() -> None:
    await asyncio.gather(*audit_runner._tasks)


async def test_audit_runs_in_background_and_is_reused(client):
    r = await client.post(
        "/api/v1/ext/research/audits", json={"url": "www.glowmedspa.com"}
    )
    assert r.status_code == 202 and r.json()["status"] == "queued"
    audit_id = r.json()["id"]
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{audit_id}")).json()
    assert done["status"] == "ready"
    assert done["domain"] == "glowmedspa.com"
    assert done["section_state"]["on_page"] == "ready"
    assert done["overview"]["provisional"] is True
    assert done["research"]["local_competitors"]["state"] == "not_run"
    again = await client.post(
        "/api/v1/ext/research/audits", json={"url": "https://glowmedspa.com/"}
    )
    assert again.status_code == 200 and again.json()["id"] == audit_id
    latest = await client.get(
        "/api/v1/ext/research/audits/latest", params={"domain": "glowmedspa.com"}
    )
    assert latest.json()["id"] == audit_id


async def test_unknown_domain_and_audit_are_not_found(client):
    for path in (
        "/api/v1/ext/research/audits/latest?domain=localhost",
        "/api/v1/ext/research/audits/not-a-uuid",
    ):
        r = await client.get(path)
        assert r.status_code == 404 and r.json()["error"]["code"] == "audit_not_found"


async def test_unsafe_url_rejected_before_any_fetch(client):
    r = await client.post(
        "/api/v1/ext/research/audits", json={"url": "http://127.0.0.1/"}
    )
    assert r.status_code == 422


async def test_unreachable_site_fails_audit(client):
    r = await client.post(
        "/api/v1/ext/research/audits", json={"url": "down.example.com"}
    )
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert (
        done["status"] == "failed" and done["error"] == "Website could not be fetched"
    )


async def test_competitors_without_key_fail_softly_and_report_builds(client):
    audit_id = (
        await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    ).json()["id"]
    await settle()
    r = await client.post(
        f"/api/v1/ext/research/audits/{audit_id}/local-competitors",
        json={"location": "Austin, TX"},
    )
    lc = r.json()["research"]["local_competitors"]
    assert r.status_code == 200 and lc["state"] == "failed" and "APIFY" in lc["error"]
    rep = (await client.get(f"/api/v1/ext/research/audits/{audit_id}/report")).json()
    assert rep["prepared_by"] == "WCM · Sam Rep" and rep["audit"]["id"] == audit_id


async def test_crawl_and_gbp_fill_in_after_home_page(client, monkeypatch):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "fake")
    monkeypatch.setattr(settings, "APIFY_API_TOKEN", "fake")

    async def fake_crawl(_http, url, *_args):
        return (
            [
                url,
                "https://glowmedspa.com/services/botox",
                "https://glowmedspa.com/about",
            ],
            {},
            True,
            [],
        )

    async def fake_gbp(_http, queries, domain, phone=None):
        assert domain == "glowmedspa.com" and "glowmedspa.com" in queries
        return {
            "matched": True,
            "name": "Glow Med Spa",
            "rating": 4.8,
            "review_count": 120,
            "phone": "(512) 555-0000",
        }, queries

    monkeypatch.setattr(site_crawl, "crawl", fake_crawl)
    monkeypatch.setattr(site_crawl, "gbp_lookup", fake_gbp)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready"
    assert (
        done["section_state"]["site"] == "ready"
        and done["section_state"]["business"] == "ready"
    )
    assert done["site"]["pages_crawled"] == 1
    assert done["business"]["gbp"]["review_count"] == 120
    assert done["business"]["gbp"]["match_reasons"] == [
        "website address",
        "phone number",
    ]
    assert done["business"]["nap"]["consistent_with_gbp"] is True


async def test_provider_failure_keeps_home_results_and_marks_partial(
    client, monkeypatch
):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "fake")

    async def broken(*_args):
        raise httpx.ConnectError("firecrawl down")

    monkeypatch.setattr(site_crawl, "crawl", broken)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "partial"
    assert done["on_page"] is not None and done["site"] is not None


async def test_home_page_is_read_by_both_and_the_browser_view_is_audited(
    client, monkeypatch
):
    """Firecrawl and the direct fetch run together; the page is Firecrawl's browser view and
    the direct read only says the site answers us (so the crawl and link checks go direct)."""
    from app.services import site_crawl

    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "fake")
    chat = HTML.replace(
        "</body>", '<iframe title="Chat with us" src="x"></iframe></body>'
    )

    async def home(_http, _url, why=None, meta=None):
        meta.update({"statusCode": 200, "url": "https://www.glowmedspa.com/"})
        return chat

    vias: list[str] = []

    async def no_crawl(_http, url, _home, via, *_args):
        vias.append(via)
        return [url], {}, True, []

    rendered_calls: list[str] = []

    async def rendered(_http, url):
        rendered_calls.append(url)

    monkeypatch.setattr(site_crawl, "scrape_home", home)
    monkeypatch.setattr(site_crawl, "scrape_rendered", rendered)
    monkeypatch.setattr(site_crawl, "crawl", no_crawl)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready" and done["on_page"] is not None
    step = next(e for e in done["trace"] if e["id"] == "home" and e["status"] == "done")
    assert step["detail"]["via"] == "firecrawl" and step["detail"]["reason"] is None
    assert (
        step["detail"]["url"] == "https://www.glowmedspa.com/"
    )  # Firecrawl's final URL
    assert vias == ["direct"]  # the site answers us: the other pages are read directly
    # the widget a script built is in the browser view: no second rendered fetch
    assert done["convert"]["chat_widget"] == "Chat widget (unidentified)"
    assert rendered_calls == []


async def test_home_page_falls_back_to_the_direct_fetch_when_firecrawl_fails(
    client, monkeypatch
):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "fake")

    async def not_found(_http, _url, why=None, meta=None):
        meta.update({"statusCode": 404})
        return HTML

    async def no_crawl(_http, url, *_args):
        return [url], {}, True, []

    monkeypatch.setattr(site_crawl, "scrape_home", not_found)
    monkeypatch.setattr(site_crawl, "crawl", no_crawl)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready"
    step = next(e for e in done["trace"] if e["id"] == "home" and e["status"] == "done")
    assert step["detail"]["via"] == "direct" and "404" in step["detail"]["reason"]


WALL = (
    '<html><head><link rel="icon" href="data:;">'
    '<meta http-equiv="refresh" content="0;/.well-known/sgcaptcha/?r=%2F"></head></html>'
)


async def test_home_page_that_is_a_bot_wall_is_never_audited(client, monkeypatch):
    """A bot-protection page must not be audited as the home page (empty title, H1...).
    Firecrawl got the wall; the direct fetch got the real page."""
    from app.services import site_crawl

    async def wall(_http, _url, why=None, meta=None):
        return WALL

    async def no_crawl(_http, url, *_args):
        return [url], {}, True, []

    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "fake")
    monkeypatch.setattr(site_crawl, "scrape_home", wall)
    monkeypatch.setattr(site_crawl, "crawl", no_crawl)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready"
    home = next(e for e in done["trace"] if e["id"] == "home" and e["status"] == "done")
    assert (
        home["detail"]["via"] == "direct"
        and "bot-protection" in home["detail"]["reason"]
    )
    page = done["on_page"]["pages"][0]
    assert page["title"].startswith("Glow Med Spa") and page["h1"] == "Glow Med Spa"
    assert "no_title" not in [i["key"] for i in page["issues"]]


async def test_home_page_bot_wall_without_a_way_around_fails_the_audit_clearly(
    client, monkeypatch
):
    from app.services import site_crawl

    async def wall(url: str, accept=None) -> tuple[str, str]:
        return WALL, url

    monkeypatch.setattr(site_audit, "fetch_html", wall)
    # no Firecrawl key: nothing can read the page
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "failed" and "bot protection" in done["error"]
    assert done["on_page"] is None  # no fake "everything is missing" report

    # a Firecrawl key whose result is a bot wall too: same clear failure
    async def still_wall(_http, _url, why=None):
        return WALL

    async def home_wall(_http, _url, why=None, meta=None):
        return WALL

    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "fake")
    monkeypatch.setattr(site_crawl, "scrape", still_wall)
    monkeypatch.setattr(site_crawl, "scrape_home", home_wall)
    r = await client.post(
        "/api/v1/ext/research/audits", json={"url": "glowmedspa.com", "force": True}
    )
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "failed" and done["on_page"] is None


async def test_ai_page_analysis_fills_topics_and_failure_marks_partial(
    client, monkeypatch
):
    from app.services import site_ai

    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "fake")
    calls = []

    async def fake_ai(_http, pages, _names):
        calls.append(list(pages))
        return {
            "services": [{"service": "Neurotoxins", "topics_present": ["What it is"]}],
            "areas_served": ["Austin"],
        }

    monkeypatch.setattr(site_ai, "analyze", fake_ai)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready" and calls == [["https://glowmedspa.com/"]]
    botox = next(
        c for c in done["site"]["services"]["clusters"] if c["service"] == "Neurotoxins"
    )
    assert botox["topics_present"] == ["What it is"]
    assert done["site"]["cities"]["claimed_not_built"] == ["Austin"]

    async def broken_ai(_http, _pages, _names):
        raise AppError(502, "upstream_error", "LLM error 500")

    monkeypatch.setattr(site_ai, "analyze", broken_ai)
    r = await client.post(
        "/api/v1/ext/research/audits", json={"url": "glowmedspa.com", "force": True}
    )
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "partial" and done["on_page"] is not None


PSI = {
    "lighthouseResult": {
        "categories": {
            "performance": {"score": 0.42},
            "seo": {"score": 0.905},
            "accessibility": {"score": 1},
            "best-practices": {"score": None},
        },
        "audits": {
            "largest-contentful-paint": {"numericValue": 3456.7},
            "cumulative-layout-shift": {"numericValue": 0.12345},
        },
    }
}


async def test_pagespeed_maps_scores_and_metrics(monkeypatch):
    from app.services import site_crawl

    seen: list[list[tuple[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.multi_items())
        return httpx.Response(200, json=PSI)

    monkeypatch.setattr(site_crawl.settings, "GOOGLE_PAGESPEED_API_KEY", "fake")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        out = await site_crawl.pagespeed(http, "https://glowmedspa.com/")
    flat = {
        "seo": 90,
        "accessibility": 100,
        "best_practices": None,
        "lcp_ms": 3457,
        "cls": 0.123,
        # this fixture has none of: the target-size / meta-viewport audits, real-visitor data
        "tap_targets_ok": None,
        "zoom_ok": None,
        "field": None,
    }
    assert out == {
        "mobile_performance": 42,
        **flat,
        "desktop": {"performance": 42, **flat},
    }
    assert sorted(v for q in seen for k, v in q if k == "strategy") == [
        "desktop",
        "mobile",
    ]
    assert all(("key", "fake") in q and ("category", "seo") in q for q in seen)


async def test_pagespeed_desktop_failure_keeps_mobile_and_logs_no_secret(
    monkeypatch, caplog
):
    from app.services import site_crawl

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["strategy"] == "desktop":
            return httpx.Response(500, json={})
        return httpx.Response(200, json=PSI)

    monkeypatch.setattr(
        site_crawl.settings, "GOOGLE_PAGESPEED_API_KEY", "sekret-key-123"
    )
    with caplog.at_level("DEBUG"):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            out = await site_crawl.pagespeed(http, "https://glowmedspa.com/")
    assert out["mobile_performance"] == 42 and out["desktop"] is None
    # httpx's own INFO request line prints the URL; ours must not
    ours = " ".join(r.getMessage() for r in caplog.records if r.name.startswith("app"))
    assert "HTTPStatusError" in ours and "500" in ours
    assert "sekret-key-123" not in ours and "googleapis" not in ours


async def test_pagespeed_mobile_failure_raises(monkeypatch):
    from app.services import site_crawl

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["strategy"] == "mobile":
            return httpx.Response(500, json={})
        return httpx.Response(200, json=PSI)

    monkeypatch.setattr(site_crawl.settings, "GOOGLE_PAGESPEED_API_KEY", "fake")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(httpx.HTTPStatusError):
            await site_crawl.pagespeed(http, "https://glowmedspa.com/")


async def test_pagespeed_runs_in_audit_when_key_set(client, monkeypatch):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "GOOGLE_PAGESPEED_API_KEY", "fake")

    async def fake_psi(_http, url):
        return {"mobile_performance": 80, "seo": 90}

    monkeypatch.setattr(site_crawl, "pagespeed", fake_psi)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready" and done["section_state"]["on_page"] == "ready"
    assert done["on_page"]["pagespeed"]["mobile_performance"] == 80


async def test_pagespeed_skipped_without_key(client, monkeypatch):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "GOOGLE_PAGESPEED_API_KEY", "")

    async def boom(_http, _url):
        raise AssertionError("PageSpeed must not be called without a key")

    monkeypatch.setattr(site_crawl, "pagespeed", boom)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready" and done["on_page"]["pagespeed"] is None


async def test_pagespeed_failure_keeps_none_and_marks_partial(
    client, monkeypatch, caplog
):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "GOOGLE_PAGESPEED_API_KEY", "fake")

    async def broken(_http, _url):
        raise httpx.ReadTimeout("psi slow key=sekret-key-123")

    monkeypatch.setattr(site_crawl, "pagespeed", broken)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    assert "sekret-key-123" not in caplog.text
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "partial" and done["section_state"]["on_page"] == "ready"
    assert done["on_page"]["pagespeed"] is None and done["site"] is not None


def folded(trace: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """What the panel does: last event per id wins."""
    return {e["id"]: e for e in trace}


async def test_trace_records_each_step_of_a_full_run(client, monkeypatch):
    from app.services import site_crawl

    for key in ("FIRECRAWL_API_KEY", "GOOGLE_PAGESPEED_API_KEY"):
        monkeypatch.setattr(settings, key, "fake")
    home = "https://glowmedspa.com"
    mapped = [home, f"{home}/services/botox", f"{home}/about", f"{home}/contact"]

    async def fake_map(_http, _url):
        return mapped

    async def fake_scrape(_http, url, why=None):
        return None if url.endswith("/about") else HTML

    async def fake_psi(_http, _url):
        return {"mobile_performance": 71}

    monkeypatch.setattr(site_crawl, "map_site", fake_map)
    monkeypatch.setattr(site_crawl, "scrape", fake_scrape)
    monkeypatch.setattr(site_crawl, "pagespeed", fake_psi)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    steps = folded(done["trace"])
    assert [
        steps[k]["status"] for k in ("home", "analyze", "map", "pick", "scrape")
    ] == ["done"] * 5
    assert steps["home"]["detail"]["via"] == "direct"
    assert steps["map"]["detail"]["count"] == 4
    assert steps["map"]["detail"]["sources"] == {"map": 4, "menu": 0, "home": 2}
    assert len(steps["map"]["detail"]["urls"]) == 4
    pick = steps["pick"]["detail"]
    groups = {g["name"]: g for g in pick["groups"]}
    assert pick["mode"] == "all"  # 3 pages: a small site is read in full
    assert groups["Services"]["picked"] == [f"{home}/services/botox"]
    # /about comes only from the map, and map pages join only the last two groups
    assert groups["About the clinic"]["picked"] == []
    assert groups["About the clinic"]["skipped"] == 1
    assert groups["Other pages"]["picked"] == [f"{home}/contact"]
    # direct reads are offline in tests, so every page falls back to Firecrawl
    assert steps["scrape"]["detail"] == {
        "ok": 2,
        "failed": 0,
        "duplicates": 0,
        "skipped": 0,
        "direct": 0,
        "firecrawl": 2,
        "timed_out": 0,
    }
    assert steps[f"page:{home}/services/botox"]["detail"]["via"] == "firecrawl"
    assert f"page:{home}/about" not in steps
    assert steps["psi"]["detail"] == {"mobile": 71, "desktop": None}
    assert steps["ai"]["status"] == "skipped" and steps["gbp"]["status"] == "skipped"
    assert steps["final"]["detail"] == {"outcome": "ready"}
    assert all(isinstance(e["at"], str) for e in done["trace"])
    assert "fake" not in json.dumps(done["trace"])  # no key ever lands in the trace


async def test_trace_marks_the_failed_step_and_final_outcome(client, monkeypatch):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "fake")

    async def down(_http, _url):
        raise httpx.ConnectError("https://api.firecrawl.dev/v2/map?key=SECRET")

    monkeypatch.setattr(site_crawl, "map_site", down)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    steps = folded(done["trace"])
    assert done["status"] == "partial"
    assert steps["map"]["status"] == "failed"
    assert steps["map"]["detail"]["error"] == "ConnectError"
    assert "SECRET" not in json.dumps(done["trace"])
    assert steps["final"]["detail"] == {"outcome": "partial"}


async def test_unreachable_site_traces_failed_home_and_final(client):
    r = await client.post(
        "/api/v1/ext/research/audits", json={"url": "down.example.com"}
    )
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    steps = folded(done["trace"])
    assert done["status"] == "failed"
    assert steps["home"]["status"] == "failed"
    assert steps["final"]["status"] == "failed"


async def test_trace_write_failure_never_breaks_the_audit(client, monkeypatch):
    async def broken(_self, _audit_id, _event):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(FakeRepo, "add_trace", broken)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready" and done["trace"] == []


async def test_score_is_computed_once_after_the_whole_audit(client, monkeypatch):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "GOOGLE_PAGESPEED_API_KEY", "fake")

    async def fake_psi(_http, _url):
        return {"mobile_performance": 95}

    monkeypatch.setattr(site_crawl, "pagespeed", fake_psi)
    seen: list[dict[str, Any]] = []
    update = FakeRepo.update

    async def spy(self, audit_id, **kw):
        seen.append(kw)
        await update(self, audit_id, **kw)

    monkeypatch.setattr(FakeRepo, "update", spy)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    home = next(u for u in seen if "on_page" in (u.get("sections") or {}))
    assert home["sections"]["overview"]["score"] is None
    assert home["state"]["overview"] == "running"
    scored = next(
        i
        for i, u in enumerate(seen)
        if "overview" in (u.get("sections") or {}) and u is not home
    )
    finished = next(i for i, u in enumerate(seen) if u.get("finished"))
    assert scored < finished and seen[scored]["state"] == {"overview": "ready"}
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    o = done["overview"]
    assert isinstance(o["score"], int) and o["grade"] in "ABCDF"
    assert len(o["categories"]) == 9 and o["categories"][0]["excluded"] is True
    assert o["provisional_reasons"] == [
        "Google Business Profile not checked"
    ]  # no Apify key
    assert done["section_state"]["overview"] == "ready"
    steps = folded(done["trace"])
    assert steps["score"]["status"] == "done"
    assert steps["score"]["label"] == "Score the audit"
    assert steps["score"]["detail"] == {"score": o["score"], "grade": o["grade"]}
    rep = (await client.get(f"/api/v1/ext/research/audits/{done['id']}/report")).json()
    assert f"{o['score']}/100" in rep["intro"]


async def test_failed_audit_gets_no_score(client):
    r = await client.post(
        "/api/v1/ext/research/audits", json={"url": "down.example.com"}
    )
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "failed" and done["overview"] is None
    assert done["section_state"]["overview"] == "failed"
    assert "score" not in folded(done["trace"])
    rep = (await client.get(f"/api/v1/ext/research/audits/{done['id']}/report")).json()
    assert "None" not in rep["intro"] and "/100" not in rep["intro"]


async def test_slow_pagespeed_is_capped_and_score_still_saved(client, monkeypatch):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "GOOGLE_PAGESPEED_API_KEY", "fake")
    monkeypatch.setattr(audit_runner, "PAGESPEED_WAIT_S", 0.05)
    cancelled = asyncio.Event()

    async def slow_psi(_http, _url):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {"mobile_performance": 99}

    monkeypatch.setattr(site_crawl, "pagespeed", slow_psi)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await asyncio.wait_for(settle(), 5)
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert cancelled.is_set()
    assert done["status"] == "partial" and done["finished_at"] is not None
    assert done["on_page"]["pagespeed"] is None
    assert done["section_state"]["on_page"] == "ready"
    o = done["overview"]
    assert o["score"] is not None and o["provisional"] is True
    assert "PageSpeed unavailable" in o["provisional_reasons"]
    steps = folded(done["trace"])
    assert steps["psi"]["status"] == "failed"
    assert steps["psi"]["detail"] == {"error": "Timed out"}
    assert steps["score"]["status"] == "done"


@pytest.mark.anyio
async def test_every_read_page_gets_on_page_checks_and_a_summary(client, monkeypatch):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "fake")
    botox = "<html><head><title>Botox</title></head><body><p>hi</p></body></html>"

    async def fake_crawl(_http, url, *_args):
        return (
            [url, "https://glowmedspa.com/botox"],
            {"https://glowmedspa.com/botox": botox},
            True,
            [],
        )

    monkeypatch.setattr(site_crawl, "crawl", fake_crawl)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    pages = {p["url"]: p for p in done["on_page"]["pages"]}
    assert pages["https://glowmedspa.com/"]["kind"] == "home"
    assert {i["key"] for i in pages["https://glowmedspa.com/botox"]["issues"]} >= {
        "no_h1",
        "thin_page",
    }
    assert done["on_page"]["summary"]["score"] < 100 and "risks" in done["schema"]
    step = folded(done["trace"])["onpage"]
    assert step["status"] == "done" and step["detail"]["pages"] == 2


# ── AI visibility endpoint ────────────────────────────────────────────────────────────────

AI = "/api/v1/ext/research/audits/{}/ai-visibility"


async def _finished_audit(client) -> str:
    audit_id = (
        await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    ).json()["id"]
    await settle()
    return audit_id


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(settings, "AI_VISIBILITY_MODELS", "ChatGPT=openai/x")


# ── Local competitors: where the search happens, and who "this clinic" is ─────────────────

LC = "/api/v1/ext/research/audits/{}/local-competitors"
GBP = {
    "name": "Glow Med Spa",
    "address": "12 Main St, Austin, TX 78701",
    "lat": 30.27,
    "lng": -97.74,
    "place_id": "ChIJ-glow",
}


@pytest.fixture
def lc_on(monkeypatch):
    monkeypatch.setattr(settings, "APIFY_API_TOKEN", "t")
    monkeypatch.setattr(
        settings, "APIFY_GMAPS_ACTOR_ID", "compass~crawler-google-places"
    )
    seen: list[tuple[str, str, Any]] = []

    async def fake_places(_http, query, location, near=None):
        seen.append((query, location, near))
        return [
            {
                "title": "Revive Medical Spa",
                "website": "https://revive.com",
                "placeId": "X1",
            },
            # the clinic's listing has no website: only the Google listing id can find it
            {"title": "Glow Med Spa", "website": None, "placeId": "ChIJ-glow"},
        ]

    monkeypatch.setattr(local_competitors, "_apify_places", fake_places)
    return seen


async def _with_gbp(client, gbp: dict[str, Any]) -> str:
    audit_id = await _finished_audit(client)
    repo = research.get_audit_repo(None)
    await repo.update(
        audit_id, sections={"business": {"gbp": gbp, "nap": {}, "socials": {}}}
    )
    return audit_id


async def test_blank_location_searches_around_the_clinic_and_flags_it_by_place_id(
    client, lc_on
):
    audit_id = await _with_gbp(client, GBP)
    r = await client.post(LC.format(audit_id), json={"query": "med spa"})
    lc = r.json()["research"]["local_competitors"]
    assert lc["state"] == "ready"
    assert lc_on == [
        ("med spa", "within 8 km of 12 Main St, Austin, TX 78701", (30.27, -97.74))
    ]
    assert lc["data"]["location"].startswith("within 8 km of")
    flags = {i["name"]: i["is_this_business"] for i in lc["data"]["items"]}
    assert flags == {"Revive Medical Spa": False, "Glow Med Spa": True}


async def test_a_typed_place_wins_over_the_clinic_coordinates(client, lc_on):
    audit_id = await _with_gbp(client, GBP)
    await client.post(
        LC.format(audit_id), json={"query": "med spa", "location": "Dallas, TX"}
    )
    assert lc_on == [("med spa", "Dallas, TX", None)]


async def test_blank_location_without_coordinates_asks_for_a_city(client, lc_on):
    audit_id = await _with_gbp(client, {**GBP, "lat": None, "lng": None})
    lc = (await client.post(LC.format(audit_id), json={})).json()["research"][
        "local_competitors"
    ]
    assert lc["state"] == "failed" and "city" in lc["error"] and lc_on == []


async def test_website_still_flags_the_clinic_when_no_place_id_is_known(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "APIFY_API_TOKEN", "t")
    monkeypatch.setattr(settings, "APIFY_GMAPS_ACTOR_ID", "x~y")

    async def places(*_a, **_k):
        return [
            {"title": "Glow", "website": "https://www.glowmedspa.com/", "placeId": "Z"}
        ]

    monkeypatch.setattr(local_competitors, "_apify_places", places)
    audit_id = await _with_gbp(client, {"name": "Glow", "lat": None, "lng": None})
    r = await client.post(LC.format(audit_id), json={"location": "Austin, TX"})
    assert r.json()["research"]["local_competitors"]["data"]["items"][0][
        "is_this_business"
    ]


async def test_apify_request_body_uses_coordinates_or_text_never_both():
    bodies: list[dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await local_competitors._apify_places(http, "med spa", "x", (30.27, -97.74))
        await local_competitors._apify_places(http, "med spa", "Austin, TX")
    near, text = bodies
    assert near["customGeolocation"] == {
        "type": "Point",
        "coordinates": [-97.74, 30.27],  # longitude first
        "radiusKm": local_competitors.CLINIC_RADIUS_KM,
    }
    assert "locationQuery" not in near
    assert text["locationQuery"] == "Austin, TX" and "customGeolocation" not in text
    assert near["maxCrawledPlacesPerSearch"] == 20


def test_gbp_profile_keeps_the_google_place_id():
    from app.services import site_crawl

    out = site_crawl._gbp_from({"title": "Glow", "placeId": "ChIJ1"}, "website", ["q"])
    assert out["place_id"] == "ChIJ1"


async def test_audit_log_ends_with_cost_and_tokens_before_the_final_step(
    client, monkeypatch
):
    """The real AI call runs through a fake OpenRouter; its tokens and dollars land in the log."""
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "fake")
    monkeypatch.setattr(settings, "RESEARCH_MODEL", "anthropic/claude-sonnet-5.5")

    def openrouter(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"services": [], "areas_served": []}'}}
                ],
                "usage": {
                    "prompt_tokens": 40_000,
                    "completion_tokens": 2_000,
                    "total_tokens": 42_000,
                    "cost": 0.0987,
                },
            },
        )

    real = httpx.AsyncClient(transport=httpx.MockTransport(openrouter))
    monkeypatch.setattr(app.state, "http_client", real, raising=False)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    await real.aclose()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready"
    ids = [e["id"] for e in done["trace"] if e["status"] != "running"]
    assert ids[-2:] == ["usage", "final"]
    step = next(e for e in done["trace"] if e["id"] == "usage")
    assert step["label"] == "Cost and tokens" and step["status"] == "done"
    d = step["detail"]
    assert (
        d["tokens"] == 42_000
        and d["prompt_tokens"] == 40_000
        and d["completion_tokens"] == 2_000
    )
    assert d["cost_usd"] == pytest.approx(0.0987) and d["calls"] == 1
    saved = research.get_audit_repo(None).rows[
        r.json()["id"]
    ]  # the Settings total reads this
    assert saved["ai_cost_micro"] == 98_700 and saved["ai_tokens"] == 42_000
    assert d["lines"] == [
        {
            "kind": "ai",
            "label": "Page analysis · claude-sonnet-5.5",
            "calls": 1,
            "tokens": 42_000,
            "prompt_tokens": 40_000,
            "completion_tokens": 2_000,
            "cost_usd": 0.0987,
        }
    ]


async def test_audit_that_spends_nothing_logs_no_cost_step(client):
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert "usage" not in [e["id"] for e in done["trace"]]


# ── Settings: AI usage of all users (owners and admins only) ────────────────────────────────


def _as(role: str):
    now = datetime.now(UTC)
    app.dependency_overrides[require_extension_access] = lambda: UserProfile(
        id=str(uuid.uuid4()),
        email="boss@example.com",
        full_name="Boss",
        avatar_url=None,
        role=role,
        is_active=True,
        admin_id=None,
        created_at=now,
        updated_at=now,
    )


async def test_ai_usage_is_refused_for_a_plain_user(client):
    r = await client.get(
        "/api/v1/ext/admin/ai-usage"
    )  # the fixture user has role "user"
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_ai_usage_for_owner_and_admin_joins_openrouter_and_tracked_spend(
    client, monkeypatch, role
):
    from app.services import openrouter_usage

    asked: list[bool] = []

    async def fake_fetch(_http, *, force=False):
        asked.append(force)
        return {
            "configured": True,
            "account": {
                "credits_usd": 85.0,
                "used_usd": 74.7198,
                "remaining_usd": 10.2802,
            },
            "key": {
                "used_usd": 28.5231,
                "today_usd": 4.9007,
                "week_usd": 11.2247,
                "month_usd": 11.2247,
                "limit_usd": 250.0,
            },
            "errors": {},
        }

    monkeypatch.setattr(openrouter_usage, "fetch", fake_fetch)
    audit_id = await _finished_audit(client)
    await research.get_audit_repo(None).set_audit_spend(audit_id, 123_456, 9_000)
    _as(role)
    body = (await client.get("/api/v1/ext/admin/ai-usage")).json()
    assert (
        body["account"]["remaining_usd"] == 10.2802
        and body["key"]["used_usd"] == 28.5231
    )
    assert body["tracked"] == {
        "total_usd": 0.1305,
        "today_usd": 0.1235,
        "week_usd": 0.1255,
        "month_usd": 0.1305,
        "audits_usd": 0.1235,
        "ai_visibility_usd": 0.007,
        "users": 2,
    }
    assert "fetched_at" in body and asked == [False]
    await client.get("/api/v1/ext/admin/ai-usage", params={"refresh": "true"})
    assert asked == [False, True]  # the refresh button skips the one-minute cache


async def test_audit_survives_an_invalid_json_ai_reply_by_asking_again(
    client, monkeypatch
):
    """The reported failure: the AI step used to end the audit 'partial' on one bad reply."""
    from app.services import llm

    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "fake")
    monkeypatch.setattr(llm, "RETRY_DELAY_S", 0)
    answers = iter(
        [
            ("Sorry, here is my analysis in prose, not JSON.", 4698, 0.1465),
            ('{"services": [], "areas_served": ["Austin"]}', 3909, 0.1178),
        ]
    )

    def openrouter(_req: httpx.Request) -> httpx.Response:
        text, out, cost = next(answers)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 49_783,
                    "completion_tokens": out,
                    "total_tokens": 49_783 + out,
                    "cost": cost,
                },
            },
        )

    real = httpx.AsyncClient(transport=httpx.MockTransport(openrouter))
    monkeypatch.setattr(app.state, "http_client", real, raising=False)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    await real.aclose()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    ai = [e for e in done["trace"] if e["id"] == "ai"][
        -1
    ]  # the log is append-only: last wins
    assert ai["status"] == "done" and done["status"] == "ready"
    assert done["site"]["cities"]["claimed_not_built"] == [
        "Austin"
    ]  # the second reply was used
    cost = next(e for e in done["trace"] if e["id"] == "usage")["detail"]
    assert (
        cost["calls"] == 2
    )  # both attempts were billed, so both are in the audit's cost
    assert cost["cost_usd"] == pytest.approx(0.1465 + 0.1178)


# ── link and redirect probes, speed issues, and the page cap ───────────────────────────────


async def test_audit_runs_the_link_probes_and_their_findings_reach_the_on_page_data(
    client, monkeypatch
):
    seen: list[dict[str, Any]] = []

    async def fake_probes(*, home, home_html, pages):
        seen.append({"home": home, "pages": list(pages)})
        return {
            "hosts": [],
            "images": [],
            "favicon": None,
            "checked": 3,
            "timed_out": 0,
            "links": [
                {
                    "url": f"{home}gone",
                    "status": 404,
                    "hops": 0,
                    "final": f"{home}gone",
                    "found_on": home,
                }
            ],
        }

    monkeypatch.setattr(probes, "run", fake_probes)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    step = [e for e in done["trace"] if e["id"] == "probe"][-1]
    assert step["status"] == "done" and step["label"] == "Check links and redirects"
    assert step["detail"] == {"checked": 3, "timed_out": 0}
    ids = [e["id"] for e in done["trace"] if e["status"] != "running"]
    assert ids.index("probe") < ids.index(
        "onpage"
    )  # the checks need what the probes found
    on = done["on_page"]
    assert "links_broken" in {i["key"] for i in on["site_issues"]}
    assert on["link_check"]["broken"][0]["found_on"] == "https://glowmedspa.com/"
    assert on["probes"]["ran"] and seen[0]["home"] == "https://glowmedspa.com/"


async def test_a_site_that_only_answers_through_firecrawl_gets_no_probes(
    client, monkeypatch
):
    """down.example.com refuses the direct fetch: Firecrawl's page is audited, the crawl reads
    through Firecrawl, and no direct link checks are made (their verdicts would be false)."""
    from app.services import site_crawl

    async def never(**_kw):
        raise AssertionError(
            "probes must not run against a site that blocks direct requests"
        )

    async def home(_http, _url, why=None, meta=None):
        return HTML

    vias: list[str] = []

    async def no_crawl(_http, url, _home, via, *_a):
        vias.append(via)
        return [url], {}, True, []

    monkeypatch.setattr(probes, "run", never)
    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "fake")
    monkeypatch.setattr(site_crawl, "scrape_home", home)
    monkeypatch.setattr(site_crawl, "crawl", no_crawl)
    r = await client.post(
        "/api/v1/ext/research/audits", json={"url": "down.example.com"}
    )
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready" and vias == ["firecrawl"]
    home_step = next(
        e for e in done["trace"] if e["id"] == "home" and e["status"] == "done"
    )
    assert home_step["detail"]["via"] == "firecrawl"
    assert "could not be fetched" in home_step["detail"]["reason"]  # why direct failed
    step = [e for e in done["trace"] if e["id"] == "probe"][-1]
    assert (
        step["status"] == "skipped"
        and "blocks direct requests" in step["detail"]["reason"]
    )


async def test_a_failing_probe_step_never_fails_the_audit(client, monkeypatch):
    async def broken(**_kw):
        raise AppError(502, "upstream_error", "boom")

    monkeypatch.setattr(probes, "run", broken)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert [e for e in done["trace"] if e["id"] == "probe"][-1]["status"] == "failed"
    assert (
        done["status"] == "ready"
        and done["on_page"] is not None
        and done["overview"]["score"] is not None
    )


async def test_phone_and_real_visitor_problems_from_pagespeed_join_the_on_page_issues(
    client, monkeypatch
):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "GOOGLE_PAGESPEED_API_KEY", "fake")

    async def fake_psi(_http, _url):
        return {
            "mobile_performance": 80,
            "seo": 90,
            "tap_targets_ok": False,
            "zoom_ok": True,
            "field": {
                "source": "origin",
                "lcp_ms": 4300,
                "lcp": "SLOW",
                "inp_ms": 150,
                "inp": "FAST",
                "cls": 0.02,
                "cls_category": "FAST",
            },
        }

    monkeypatch.setattr(site_crawl, "pagespeed", fake_psi)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    on = done["on_page"]
    got = {i["key"]: i["severity"] for i in on["site_issues"]}
    assert got["tap_targets_small"] == "medium" and got["field_lcp_poor"] == "high"
    assert (
        "viewport_blocks_zoom" not in got and "field_inp_poor" not in got
    )  # fine, so not reported
    page_issues = [i for p in on["pages"] for i in p["issues"]]
    assert on["summary"]["high"] == sum(
        1 for i in page_issues + on["site_issues"] if i["severity"] == "high"
    )
    assert on["pagespeed"]["field"]["lcp"] == "SLOW"


def test_the_page_cap_is_sixty_and_the_read_time_scales_with_it():
    fields = type(settings).model_fields
    assert (
        fields["CRAWL_MAX_PAGES"].default == 60 and fields["AI_MAX_PAGES"].default == 60
    )
    assert (
        fields["CRAWL_BUDGET_S"].default == 60.0
    )  # about a second per page, as before


def test_audit_always_starts_at_the_site_root(monkeypatch: pytest.MonkeyPatch):
    seen: list[str] = []

    class Repo:
        async def latest(self, *_a: Any, **_k: Any) -> None:
            return None

        async def create(self, _u: str, url: str, *_a: Any) -> dict[str, str]:
            seen.append(url)
            return {"id": "1"}

    async def no_run(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(audit_runner, "_run", no_run)
    asyncio.run(
        audit_runner.start(
            Repo(), None, "u", "https://Example.com/a/b?x=1#f", False, {}
        )  # type: ignore[arg-type]
    )
    assert seen == ["https://example.com/"]


def test_one_site_runs_once_even_with_www_force_and_two_clicks(
    monkeypatch: pytest.MonkeyPatch,
):
    rows: list[dict[str, str]] = []

    class Repo:
        async def latest(self, domain: str, fresh_only: bool = False):
            hit = [r for r in rows if r["domain"] == domain]
            return hit[-1] if hit else None

        async def create(self, _u: str, url: str, domain: str, *_a: Any):
            await asyncio.sleep(
                0
            )  # a real insert yields; this is where a second click got in
            row = {
                "id": str(len(rows)),
                "url": url,
                "domain": domain,
                "status": "running",
            }
            rows.append(row)
            return row

    async def no_run(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(audit_runner, "_run", no_run)

    async def go():
        return await asyncio.gather(
            audit_runner.start(Repo(), None, "u", "www.Example.com", False, {}),  # type: ignore[arg-type]
            audit_runner.start(Repo(), None, "u", "example.com", True, {}),  # type: ignore[arg-type]
            audit_runner.start(Repo(), None, "u", "https://example.com/x", True, {}),  # type: ignore[arg-type]
        )

    out = asyncio.run(go())
    assert [created for _, created in out] == [True, False, False]
    assert len(rows) == 1 and rows[0]["domain"] == "example.com"


async def test_start_up_fails_a_run_it_cannot_resume_and_keeps_going(
    monkeypatch: pytest.MonkeyPatch,
):
    failed: list[str] = []
    spawned: list[str] = []

    class Repo:
        async def running_full_runs(self) -> list[str]:
            return ["gone", "boom", "ok"]

        async def get_ai_run(self, run_id: str) -> dict[str, str] | None:
            if run_id == "boom":
                raise RuntimeError("db down")
            return {"audit_id": run_id}

        async def get(self, audit_id: str) -> dict[str, str] | None:
            return None if audit_id == "gone" else {"id": audit_id}

        async def save_ai_run(self, run_id: str, **kw: Any) -> None:
            failed.append(f"{run_id}:{kw['status']}")

    monkeypatch.setattr(ai_runs, "to_wire", lambda row: row)
    monkeypatch.setattr(
        ai_runs, "spawn", lambda _r, _h, run_id, _a: spawned.append(run_id)
    )
    n = await ai_runs.resume_full_runs(Repo(), None)  # type: ignore[arg-type]
    assert n == 1 and spawned == ["ok"]
    assert failed == [
        "gone:failed"
    ]  # a run with no audit would block its audit for ever


# ── full AI visibility report: API ──────────────────────────────────────────────────────────

FULL = "/api/v1/ext/research/audits/{}/ai-visibility/full"


def client_repo(c) -> FakeRepo:
    return c.repo


def av_cap() -> int:
    return ai_visibility.ANSWER_TEXT_CAP


@pytest.fixture
def full_jobs(monkeypatch):
    """Replace the job with one that records its start and can be held open."""
    started: list[str] = []
    release = asyncio.Event()

    async def fake_job(repo, http, run_id, audit):
        started.append(run_id)
        await release.wait()
        await repo.save_ai_run(run_id, status="ready", finished=True)

    monkeypatch.setattr(ai_report, "run_job", fake_job)
    monkeypatch.setattr(settings, "AI_VISIBILITY_FULL_PROMPTS", 12)
    monkeypatch.setattr(settings, "AI_VISIBILITY_FULL_RUNS", 2)
    monkeypatch.setattr(settings, "AI_VISIBILITY_FULL_MAX_CALLS", 400)
    return started, release


async def test_full_report_returns_202_at_once_and_freezes_its_shape(
    client, ai_on, full_jobs
):
    started, release = full_jobs
    audit_id = await _finished_audit(client)
    r = await client.post(FULL.format(audit_id), json={})
    assert r.status_code == 202
    assert r.json()["research"]["ai_visibility"]["state"] == "running"
    await asyncio.sleep(
        0.01
    )  # the job is held open on purpose: settle() would wait for it
    assert len(started) == 1
    cfg = next(iter(client_repo(client).runs.values()))["config"]
    # engines come from AI_VISIBILITY_MODELS, size from the env, versions are recorded
    assert (cfg["n_prompts"], cfg["runs"]) == (12, 2)
    assert cfg["calls"] == 12 * len(cfg["engines"]) * 2 and cfg["scoring_version"] == 1
    release.set()


async def test_full_report_double_click_is_refused(client, ai_on, full_jobs):
    _, release = full_jobs
    audit_id = await _finished_audit(client)
    assert (await client.post(FULL.format(audit_id), json={})).status_code == 202
    again = await client.post(FULL.format(audit_id), json={})
    assert (
        again.status_code == 409 and again.json()["error"]["code"] == "already_running"
    )
    release.set()


async def test_full_report_refuses_a_run_that_would_make_too_many_calls(
    client, ai_on, full_jobs, monkeypatch
):
    monkeypatch.setattr(settings, "AI_VISIBILITY_FULL_MAX_CALLS", 10)
    audit_id = await _finished_audit(client)
    r = await client.post(FULL.format(audit_id), json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_many_calls"
    assert client_repo(client).runs == {}  # nothing was created, nothing paid


async def test_full_report_uses_the_callers_own_questions(client, ai_on, full_jobs):
    audit_id = await _finished_audit(client)
    r = await client.post(
        FULL.format(audit_id),
        json={"prompts": ["  best botox  ", "best botox", "", "top spa"]},
    )
    assert r.status_code == 202
    cfg = next(iter(client_repo(client).runs.values()))["config"]
    assert cfg["prompts"] == ["best botox", "top spa"] and cfg["n_prompts"] == 2
    assert cfg["prompts_source"] == "user"


async def test_full_report_needs_the_models_set_up(client, full_jobs):
    audit_id = await _finished_audit(client)
    r = await client.post(FULL.format(audit_id), json={})
    assert (
        r.status_code == 503 and "AI_VISIBILITY_MODELS" in r.json()["error"]["message"]
    )


async def test_full_report_stops_at_the_daily_budget(client, ai_on, full_jobs):
    client_repo(client).spent = 10_000_000
    audit_id = await _finished_audit(client)
    r = await client.post(FULL.format(audit_id), json={})
    assert r.status_code == 429 and r.json()["error"]["code"] == "budget_reached"


async def test_answers_endpoint_pages_through_one_full_report(client, ai_on, full_jobs):
    repo = client_repo(client)
    audit_id = await _finished_audit(client)
    await client.post(FULL.format(audit_id), json={"prompts": ["best botox"]})
    run_id = next(iter(repo.runs))
    repo.answers_page = [
        {
            "prompt_idx": 0,
            "engine": "ChatGPT",
            "run_no": 1,
            "status": "ok",
            "text": "x" * 20000,
            "urls": ["https://a.example"],
            "error": None,
            "facts": {"brands": {}},
        }
    ]
    r = await client.get(
        f"/api/v1/ext/research/ai-visibility/runs/{run_id}/answers?engine=ChatGPT&prompt=0&limit=5"
    )
    body = r.json()
    assert r.status_code == 200 and body["prompts"] == ["best botox"]
    assert (
        body["items"][0]["engine"] == "ChatGPT"
        and len(body["items"][0]["text"]) <= av_cap() + 1
    )
    assert repo.last_page == {
        "engine": "ChatGPT",
        "prompt_idx": 0,
        "limit": 5,
        "offset": 0,
    }
    assert (
        await client.get(
            f"/api/v1/ext/research/ai-visibility/runs/{run_id}/answers?limit=999"
        )
    ).status_code == 422


async def test_answers_endpoint_hides_lite_runs_and_unknown_ids(client, ai_on):
    repo = client_repo(client)
    audit_id = await _finished_audit(client)
    lite_id = str(uuid.uuid4())  # an old row from before the quick check was removed
    repo.runs[lite_id] = {
        "audit_id": audit_id,
        "state": "ready",
        "data": None,
        "error": None,
        "kind": "lite",
        "config": {},
    }
    for rid in (lite_id, str(uuid.uuid4())):
        r = await client.get(f"/api/v1/ext/research/ai-visibility/runs/{rid}/answers")
        assert r.status_code == 404 and r.json()["error"]["code"] == "run_not_found"


async def test_start_up_resumes_full_runs(client, ai_on, full_jobs):
    started, release = full_jobs
    repo = client_repo(client)
    audit_id = await _finished_audit(client)
    await repo.create_ai_run(audit_id, "u", {"calls": 1})
    n = await ai_runs.resume_full_runs(repo, httpx.AsyncClient())
    await asyncio.sleep(0.01)
    assert n == 1 and len(started) == 1
    release.set()


# ── full report step 1: write the questions, then approve ─────────────────────────────────

QUESTIONS = "/api/v1/ext/research/audits/{}/ai-visibility/questions"


@pytest.fixture
def writer(monkeypatch):
    seen: list[int] = []

    async def fake(_http, _audit, n, _spent):
        seen.append(n)
        return [f"best med spa in Austin {i}" for i in range(n)], "llm"

    monkeypatch.setattr(ai_report, "make_prompts", fake)
    return seen


async def test_questions_are_written_and_sized_but_nothing_starts(
    client, ai_on, full_jobs, writer
):
    started, _ = full_jobs
    audit_id = await _finished_audit(client)
    r = await client.post(QUESTIONS.format(audit_id))
    body = r.json()
    assert r.status_code == 200 and writer == [12]
    assert len(body["prompts"]) == 12 and body["source"] == "llm"
    assert body["runs"] == 2 and body["max_questions"] == 12 and body["engines"]
    assert client_repo(client).runs == {} and started == []  # no run, no paid answers


async def test_writing_questions_is_allowed_when_the_daily_budget_is_used_up(
    client, ai_on, full_jobs, writer
):
    client_repo(client).spent = 10_000_000
    audit_id = await _finished_audit(client)
    assert (await client.post(QUESTIONS.format(audit_id))).status_code == 200
    # but the paid run itself is still refused
    r = await client.post(
        FULL.format(audit_id), json={"prompts": ["best botox in Austin"]}
    )
    assert r.status_code == 429


async def test_questions_need_the_setup_and_a_finished_audit(client, full_jobs, writer):
    audit_id = await _finished_audit(client)
    r = await client.post(QUESTIONS.format(audit_id))
    assert (
        r.status_code == 503 and "AI_VISIBILITY_MODELS" in r.json()["error"]["message"]
    )
    assert writer == []


async def test_the_approved_questions_are_used_exactly(client, ai_on, full_jobs):
    audit_id = await _finished_audit(client)
    approved = [
        "best botox in Austin",
        "  top   rated   spa  in Austin ",
        "best botox in Austin",
        "fillers near me",
    ]
    r = await client.post(FULL.format(audit_id), json={"prompts": approved})
    assert r.status_code == 202
    cfg = next(iter(client_repo(client).runs.values()))["config"]
    # trimmed, spaces collapsed, duplicate removed, order kept, nothing added or dropped
    assert cfg["prompts"] == [
        "best botox in Austin",
        "top rated spa in Austin",
        "fillers near me",
    ]
    assert cfg["n_prompts"] == 3 and cfg["prompts_source"] == "user"
    assert cfg["calls"] == 3 * len(cfg["engines"]) * cfg["runs"]


async def test_a_question_that_names_the_clinic_is_refused_not_silently_dropped(
    client, ai_on, full_jobs
):
    audit_id = await _finished_audit(client)
    await client_repo(client).update(
        audit_id,
        sections={
            "business": {"gbp": {"name": "Glow Med Spa"}, "nap": {}, "socials": {}}
        },
    )
    r = await client.post(
        FULL.format(audit_id), json={"prompts": ["best botox", "Glow Med Spa reviews"]}
    )
    err = r.json()["error"]
    assert r.status_code == 422 and err["code"] == "question_names_clinic"
    assert "Glow Med Spa reviews" in err["message"]
    assert client_repo(client).runs == {}


async def test_more_questions_than_the_env_allows_is_refused_not_cut(
    client, ai_on, full_jobs
):
    audit_id = await _finished_audit(client)
    r = await client.post(
        FULL.format(audit_id),
        json={"prompts": [f"question {i} in Austin" for i in range(13)]},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_many_questions"
    assert "Remove 1" in r.json()["error"]["message"] and client_repo(client).runs == {}


async def test_whole_audit_grades_the_areas_a_clinic_claims(client, monkeypatch):
    """A Solene-like site through the real pipeline (only the network is faked): city pages in
    root folders, a state hub, a thin page, a mention, and a city with nothing."""
    from app.services import site_ai, site_crawl

    for key in ("FIRECRAWL_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setattr(settings, key, "fake")
    home = "https://glowmedspa.com"

    def words(prefix: str, n: int = 400) -> str:
        return " ".join(f"{prefix}{i}" for i in range(n))

    def page(title: str, h1: str, body: str = "", links: str = "") -> str:
        return (
            f'<html lang="en"><head><title>{title}</title>'
            '<meta name="viewport" content="width=device-width"></head><body>'
            f'<nav><a href="/tampa/">Tampa</a><a href="/ocala/">Ocala</a></nav>'
            f"<h1>{h1}</h1><main>{body} {links}</main>"
            "<footer>Serving Tampa, Ocala and Naples</footer></body></html>"
        )

    site = {
        f"{home}/": page("Glow Med Spa", "Glow", words("h", 50)),
        f"{home}/tampa/": page("Med spa in Tampa", "Tampa med spa", words("t")),
        f"{home}/ocala/": page("Ocala", "Ocala", "tiny page"),
        f"{home}/florida/": page(
            "Florida care",
            "Care across Florida",
            words("f", 350),
            '<a href="/tampa/">T</a> <a href="/ocala/">O</a>',
        ),
    }

    async def fake_map(_http, _url):
        return list(site)

    async def fake_scrape(_http, url, why=None):
        return site.get(url)

    async def fake_ai(_http, _pages, _names):
        return {"areas_served": ["Tampa", "Ocala", "Naples", "Miami", "Florida"]}

    monkeypatch.setattr(site_crawl, "map_site", fake_map)
    monkeypatch.setattr(site_crawl, "scrape", fake_scrape)
    monkeypatch.setattr(site_ai, "analyze", fake_ai)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready"
    cities = done["site"]["cities"]
    by = {a["name"]: a for a in cities["areas"]}
    assert {n: a["status"] for n, a in by.items()} == {
        "Tampa": "covered",
        "Ocala": "needs_work",
        "Naples": "mentioned",  # only in the footer of every page
        "Miami": "missing",
        "Florida": "covered",
    }
    assert by["Ocala"]["issues"] == ["thin"]
    assert cities["claimed_not_built"] == ["Naples", "Miami"]
    assert (
        cities["hub_page"] is True
    )  # /florida/ links Tampa and Ocala from its own content
    assert cities["pages_found"] == len(cities["city_pages"]) == 3
    assert done["overview"]["score"] is not None  # scoring ran with the new area data
    # the report endpoint carries the same data, as plain JSON
    rep = (
        await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}/report")
    ).json()
    assert rep["audit"]["site"]["cities"]["areas"] == cities["areas"]


async def test_leftover_text_a_script_replaces_is_not_reported(monkeypatch):
    """Viva /specials: one "Title Goes Here / Lorem ipsum" slide in the HTML, real cards once
    the page's script runs. Re-read as a browser shows it, the finding is dropped."""
    from app.services import site_crawl

    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "fake")
    rendered = {
        "https://g.example/specials": "<html><body><h1>Specials</h1><p>Botox $11</p></body></html>",
        "https://g.example/about": "<html><body><p>Lorem ipsum dolor sit amet</p></body></html>",
    }

    async def fake_rendered(_http, url):
        return rendered[url]

    monkeypatch.setattr(site_crawl, "scrape_rendered", fake_rendered)
    sections = {
        "site": {
            "unfinished_pages": [
                {
                    "url": "https://g.example/specials",
                    "reason": "Leftover",
                    "counted": True,
                },
                {
                    "url": "https://g.example/about",
                    "reason": "Leftover",
                    "counted": True,
                },
                {
                    "url": "https://g.example/test",
                    "reason": "Test page",
                    "counted": False,
                },
            ],
            "placeholder_pages": [
                "https://g.example/test",
                "https://g.example/specials",
                "https://g.example/about",
            ],
        }
    }
    await audit_runner._confirm_leftover_text(None, sections)  # type: ignore[arg-type]
    assert [p["url"] for p in sections["site"]["unfinished_pages"]] == [
        "https://g.example/about",  # still there after the script ran: real
        "https://g.example/test",  # not a leftover-text finding: not re-read
    ]
    assert "https://g.example/specials" not in sections["site"]["placeholder_pages"]
    assert "https://g.example/about" in sections["site"]["placeholder_pages"]


def test_the_clinics_phone_comes_from_the_contact_page_when_the_home_page_has_none():
    """Viva: no phone on the home page, a tel: link on /contact. Without it the phone could
    not be compared with the Google profile's ("Not compared")."""
    sections = {"business": {"nap": {"phone": None}}}
    crawled = {
        "https://v.example/botox": '<a href="tel:+1 (555) 000-1111">Call</a>',
        "https://v.example/contact": '<a href="tel:+14129197707">Call us</a>',
    }
    audit_runner._phone_from_pages(sections, crawled)
    assert sections["business"]["nap"]["phone"] == "412-919-7707"
    sections = {"business": {"nap": {"phone": "678-261-7700"}}}  # the home page's wins
    audit_runner._phone_from_pages(sections, crawled)
    assert sections["business"]["nap"]["phone"] == "678-261-7700"


async def test_an_audit_that_hangs_is_stopped_and_can_be_run_again(client, monkeypatch):
    """A step that never answers used to hold the audit `running` for ever, and with it one of
    the three audit slots; Re-run then returned the same stuck audit."""
    monkeypatch.setattr(settings, "AUDIT_MAX_S", 0.05)
    hang = True

    async def steps(*_a, **_k):
        if hang:
            await asyncio.sleep(10)
        return True

    monkeypatch.setattr(audit_runner, "_steps", steps)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    first = r.json()["id"]
    await settle()
    stuck = (await client.get(f"/api/v1/ext/research/audits/{first}")).json()
    assert stuck["status"] == "failed" and "took too long" in stuck["error"]
    assert all(v == "failed" for v in stuck["section_state"].values())

    hang = False  # the provider is back: Re-run starts a NEW audit, not the stuck one
    again = await client.post(
        "/api/v1/ext/research/audits", json={"url": "glowmedspa.com", "force": True}
    )
    assert again.json()["id"] != first
    await settle()
    done = (
        await client.get(f"/api/v1/ext/research/audits/{again.json()['id']}")
    ).json()
    assert done["status"] == "ready"


async def _audit_with_gbp(client, monkeypatch, lookup):
    from app.services import site_crawl

    monkeypatch.setattr(settings, "APIFY_API_TOKEN", "t")
    monkeypatch.setattr(settings, "APIFY_GMAPS_ACTOR_ID", "a")
    monkeypatch.setattr(site_crawl, "gbp_lookup", lookup)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    return (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()


async def test_a_searched_profile_that_was_not_found_is_not_the_same_as_one_never_checked(
    client, monkeypatch
):
    async def none_found(_http, queries, _domain, _phone=None):
        return None, queries[:2]

    done = await _audit_with_gbp(client, monkeypatch, none_found)
    assert done["business"]["gbp_status"] == "not_found"
    assert "Searched Google Maps" in done["business"]["gbp_note"]
    assert (
        done["overview"]["provisional_reasons"][0] == "No Google Business Profile found"
    )


async def test_a_failed_profile_search_says_not_checked_never_not_found(
    client, monkeypatch
):
    async def broken(_http, _queries, _domain, _phone=None):
        raise httpx.ConnectError("down")

    done = await _audit_with_gbp(client, monkeypatch, broken)
    assert done["business"]["gbp_status"] == "not_checked"
    assert "failed" in done["business"]["gbp_note"]
    assert done["status"] == "partial"
    assert (
        done["overview"]["provisional_reasons"][0]
        == "Google Business Profile not checked"
    )
