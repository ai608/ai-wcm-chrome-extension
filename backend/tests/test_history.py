from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.api.v1.history import get_brief_repository
from app.core.config import settings
from app.core.dependencies import require_extension_access
from app.main import app
from app.services import ghl, llm

pytestmark = pytest.mark.anyio
LOC = "loc1"
CATALOG = [
    {"id": "lc", "name": "Last Call Summary", "fieldKey": "contact.last_call_summary"},
    {"id": "sdr", "name": "SDR name", "fieldKey": "contact.sdr_name"},
]
CONTACT = {
    "id": "c1",
    "locationId": LOC,
    "companyName": "Glow Med Spa",
    "customFields": [
        {"id": "lc", "value": "Asked for a callback after the holidays"},
        {"id": "sdr", "value": "Lia"},
        {"id": "x", "value": "ignored"},
    ],
}
NOTES = {
    "notes": [
        {
            "id": "n1",
            "body": "<p>Prospect research</p><br>Site is live",
            "dateAdded": "2026-08-23T21:07:00.000Z",
        },
        {"id": "n2", "body": "  ", "dateAdded": "2026-08-24T00:00:00.000Z"},
    ]
}
CONVS = {"conversations": [{"id": "v1", "lastMessageDate": 1790000000000}]}
MESSAGES = {
    "messages": {
        "messages": [
            {
                "id": "m1",
                "messageType": "TYPE_CALL",
                "direction": "outbound",
                "status": "completed",
                "dateAdded": "2026-10-28T15:00:00.000Z",
                "meta": {"call": {"duration": 180}},
            },
            {
                "id": "m2",
                "messageType": "TYPE_SMS",
                "direction": "inbound",
                "body": "Call me after 3",
                "dateAdded": "2026-10-29T15:00:00.000Z",
            },
            {
                "id": "m3",
                "messageType": "TYPE_ACTIVITY_OPPORTUNITY",
                "dateAdded": "2026-10-30T00:00:00Z",
            },
        ]
    }
}
OPPS = {
    "opportunities": [
        {
            "id": "o1",
            "name": "Glow",
            "monetaryValue": 2400,
            "status": "open",
            "pipelineId": "p",
            "pipelineStageId": "s",
        }
    ]
}
PIPES = {
    "pipelines": [{"id": "p", "name": "Sales", "stages": [{"id": "s", "name": "Demo"}]}]
}
state: dict = {}


def fake_ghl(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path in state.get("fail", ()):
        return httpx.Response(401)
    routes = {
        "/locations/loc1/customFields": {"customFields": CATALOG},
        "/contacts/c1": {"contact": CONTACT},
        "/contacts/other": {"contact": {**CONTACT, "locationId": "x"}},
        "/contacts/c1/notes": NOTES,
        "/conversations/search": CONVS,
        "/conversations/v1/messages": MESSAGES,
        "/opportunities/search": OPPS,
        "/opportunities/pipelines": PIPES,
    }
    return (
        httpx.Response(200, json=routes[path])
        if path in routes
        else httpx.Response(404)
    )


class FakeRepo:
    def __init__(self) -> None:
        self.rows: dict = {}
        self.saved: list = []

    async def find(self, contact_id, digest, version):
        return self.rows.get((contact_id, digest, version))

    async def latest(self, contact_id):
        mine = [r for k, r in self.rows.items() if k[0] == contact_id]
        return mine[-1] if mine else None

    async def save(self, contact_id, digest, version, model, text, user, cost, tokens):
        now = datetime.now(UTC)
        self.rows[(contact_id, digest, version)] = {"text": text, "created_at": now}
        self.saved.append((user, cost, tokens))
        return now


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def env(monkeypatch):
    monkeypatch.setattr(settings, "GHL_PIT", "pit")
    monkeypatch.setattr(settings, "GHL_SALES_LOCATION_ID", LOC)
    monkeypatch.setattr(settings, "RESEARCH_MODEL", "m/x")
    monkeypatch.setattr(ghl, "_catalog", None)
    state.clear()
    calls: list = []

    async def fake_llm(http, system, user, *, usage_out=None, **kw):
        calls.append(user)
        if state.get("llm_fail"):
            raise RuntimeError("model down")
        usage_out.update({"cost_micro": 1200, "tokens": 90})
        return {"brief": "Lia called Oct 28; they asked for a call after 3."}

    monkeypatch.setattr(llm, "chat_json", fake_llm)
    repo = FakeRepo()
    app.dependency_overrides[require_extension_access] = lambda: SimpleNamespace(
        id="u1", role="sdr"
    )
    app.dependency_overrides[get_brief_repository] = lambda: repo
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake_ghl)) as http:
        app.state.http_client = http
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c:
            yield c, repo, calls
    app.dependency_overrides.clear()


async def test_history_shape(env):
    c, repo, calls = env
    r = await c.get("/api/v1/ext/contacts/c1/history")
    assert r.status_code == 200
    body = r.json()
    assert [a["id"] for a in body["activities"]] == [
        "msg:m2",
        "msg:m1",
        "note:n1",
    ]  # newest first, empty note and non-call/sms/email dropped
    assert body["activities"][1]["body"] == "Outbound call · 3 min · completed"
    assert (
        body["activities"][2]["body"] == "Prospect research\n\nSite is live"
    )  # tags stripped, breaks kept
    assert body["activities"][0]["source"] == "Contact"
    assert body["opportunities"] == [
        {
            "id": "o1",
            "name": "Glow",
            "monetary_value": 2400,
            "status": "open",
            "pipeline_name": "Sales",
            "stage_name": "Demo",
        }
    ]
    assert body["last_contacted_at"].startswith(
        "2026-10-28"
    )  # the outbound call, not the inbound SMS
    assert body["brief"]["text"].startswith("Lia called")
    assert (
        "Last call summary" in calls[0] and "SDR" in calls[0]
    )  # custom fields found by name
    assert repo.saved == [("u1", 1200, 90)]  # spend is recorded


async def test_brief_cached_until_facts_change(env):
    c, repo, calls = env
    await c.get("/api/v1/ext/contacts/c1/history")
    await c.get("/api/v1/ext/contacts/c1/history")
    assert len(calls) == 1 and len(repo.saved) == 1
    CONTACT["customFields"][0]["value"] = "Not interested"
    try:
        await c.get("/api/v1/ext/contacts/c1/history")
    finally:
        CONTACT["customFields"][0]["value"] = "Asked for a callback after the holidays"
    assert len(calls) == 2  # new facts, new brief row


async def test_brief_failure_keeps_the_tab(env):
    c, _repo, _calls = env
    state["llm_fail"] = True
    r = await c.get("/api/v1/ext/contacts/c1/history")
    assert r.status_code == 200
    assert r.json()["brief"] is None and len(r.json()["activities"]) == 3


async def test_brief_failure_falls_back_to_last_brief(env):
    c, _repo, _calls = env
    await c.get("/api/v1/ext/contacts/c1/history")
    CONTACT["customFields"][0]["value"] = "Changed"
    state["llm_fail"] = True
    try:
        r = await c.get("/api/v1/ext/contacts/c1/history")
    finally:
        CONTACT["customFields"][0]["value"] = "Asked for a callback after the holidays"
    assert r.json()["brief"]["text"].startswith("Lia called")


async def test_missing_scope_drops_one_source_only(env):
    c, _repo, _calls = env
    state["fail"] = {"/opportunities/search", "/conversations/search"}
    r = await c.get("/api/v1/ext/contacts/c1/history")
    assert r.status_code == 200
    body = r.json()
    assert body["opportunities"] == []
    assert [a["id"] for a in body["activities"]] == ["note:n1"]


async def test_no_facts_no_model_call(env, monkeypatch):
    c, _repo, calls = env
    monkeypatch.setitem(CONTACT, "customFields", [])
    state["fail"] = {
        "/contacts/c1/notes",
        "/conversations/search",
        "/opportunities/search",
    }
    r = await c.get("/api/v1/ext/contacts/c1/history")
    assert r.json()["brief"] is None and calls == []


async def test_wrong_location(env):
    c, _repo, calls = env
    r = await c.get("/api/v1/ext/contacts/other/history")
    assert r.status_code == 403 and r.json()["error"]["code"] == "wrong_location"
    assert calls == []
