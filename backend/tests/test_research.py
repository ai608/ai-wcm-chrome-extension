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
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as c:
        yield c
    app.dependency_overrides.clear()


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

    async def fake_crawl(_http, url):
        return [
            url,
            "https://glowmedspa.com/services/botox",
            "https://glowmedspa.com/about",
        ], {}

    async def fake_gbp(_http, query, domain):
        assert domain == "glowmedspa.com"
        return {
            "matched": True,
            "name": "Glow Med Spa",
            "rating": 4.8,
            "review_count": 120,
            "phone": "(512) 555-0000",
        }

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
    # the home page link text is "Call", so there is no number to compare
    assert done["business"]["nap"]["consistent_with_gbp"] is None


async def test_provider_failure_keeps_home_results_and_marks_partial(
    client, monkeypatch
):
    from app.services import site_crawl

    monkeypatch.setattr(research.settings, "FIRECRAWL_API_KEY", "fake")

    async def broken(_http, _url):
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

    async def no_crawl(_http, url):
        return [url], {}

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

    async def fake_ai(_http, pages):
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

    async def broken_ai(_http, _pages):
        raise research.AppError(502, "upstream_error", "LLM error 500")

    monkeypatch.setattr(site_ai, "analyze", broken_ai)
    r = await client.post(
        "/api/v1/ext/research/audits", json={"url": "glowmedspa.com", "force": True}
    )
    await settle()
    done = (await client.get(f"/api/v1/ext/research/audits/{r.json()['id']}")).json()
    assert done["status"] == "partial" and done["on_page"] is not None
