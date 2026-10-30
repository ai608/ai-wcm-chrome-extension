import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.api.v1 import research
from app.core.dependencies import require_extension_access
from app.main import app
from app.models.user import UserProfile
from app.repositories.audit_repository import COLUMNS
from app.services import site_audit

pytestmark = pytest.mark.anyio

HTML = """<html lang="en"><head><title>Glow Med Spa Austin | Botox and Fillers</title>
<meta name="viewport" content="width=device-width"></head><body><h1>Glow Med Spa</h1>
<a href="/services/botox">Botox</a><a href="tel:+15125550000">Call</a></body></html>"""


class Row(dict[str, Any]):
    pass


class FakeRepo:
    def __init__(self) -> None:
        self.rows: dict[str, Row] = {}

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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(research, "_repo", lambda _request: repo)

    async def fake_fetch(url: str) -> tuple[str, str]:
        if "down" in url:
            raise research.AppError(
                422, "site_unreachable", "Website could not be fetched"
            )
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
        yield c
    app.dependency_overrides.clear()
    await shared.aclose()


async def settle() -> None:
    await asyncio.gather(*research._tasks)


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

    monkeypatch.setattr(research.settings, "FIRECRAWL_API_KEY", "fake")
    monkeypatch.setattr(research.settings, "APIFY_API_TOKEN", "fake")

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

    monkeypatch.setattr(research.settings, "FIRECRAWL_API_KEY", "fake")

    async def broken(*_args):
        raise httpx.ConnectError("firecrawl down")

    monkeypatch.setattr(site_crawl, "crawl", broken)
    r = await client.post("/api/v1/ext/research/audits", json={"url": "glowmedspa.com"})
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "partial"
    assert done["on_page"] is not None and done["site"] is not None


async def test_blocked_home_page_falls_back_to_firecrawl(client, monkeypatch):
    from app.services import site_crawl

    monkeypatch.setattr(research.settings, "FIRECRAWL_API_KEY", "fake")

    async def fake_scrape(_http, _url):
        return HTML

    async def no_crawl(_http, url, *_args):
        return [url], {}, True, []

    monkeypatch.setattr(site_crawl, "scrape", fake_scrape)
    monkeypatch.setattr(site_crawl, "crawl", no_crawl)
    r = await client.post(
        "/api/v1/ext/research/audits", json={"url": "down.example.com"}
    )
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "ready" and done["on_page"] is not None


async def test_ai_page_analysis_fills_topics_and_failure_marks_partial(
    client, monkeypatch
):
    from app.services import site_ai

    monkeypatch.setattr(research.settings, "OPENROUTER_API_KEY", "fake")
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
        raise research.AppError(502, "upstream_error", "LLM error 500")

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

    monkeypatch.setattr(research.settings, "GOOGLE_PAGESPEED_API_KEY", "fake")

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

    monkeypatch.setattr(research.settings, "GOOGLE_PAGESPEED_API_KEY", "")

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

    monkeypatch.setattr(research.settings, "GOOGLE_PAGESPEED_API_KEY", "fake")

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
        monkeypatch.setattr(research.settings, key, "fake")
    home = "https://glowmedspa.com"
    mapped = [home, f"{home}/services/botox", f"{home}/about", f"{home}/contact"]

    async def fake_map(_http, _url):
        return mapped

    async def fake_scrape(_http, url):
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

    monkeypatch.setattr(research.settings, "FIRECRAWL_API_KEY", "fake")

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

    monkeypatch.setattr(research.settings, "GOOGLE_PAGESPEED_API_KEY", "fake")

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
    assert o["provisional_reasons"] == ["No Google Business Profile found"]
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

    monkeypatch.setattr(research.settings, "GOOGLE_PAGESPEED_API_KEY", "fake")
    monkeypatch.setattr(research, "PAGESPEED_WAIT_S", 0.05)
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
