import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.api.v1 import ext
from app.core.config import settings
from app.core.dependencies import require_extension_access
from app.main import app
from app.models.user import UserProfile
from app.services import ghl

pytestmark = pytest.mark.anyio
LOC = "loc1"
URL = "/api/v1/ext/contacts/c1/outcome"
_NOW = datetime.now(UTC)
USER = UserProfile(
    id=str(uuid.uuid4()),
    email="rep@example.com",
    full_name="Sam Rep",
    avatar_url=None,
    role="user",
    is_active=True,
    admin_id=None,
    created_at=_NOW,
    updated_at=_NOW,
)


class FakeCrm:
    """A CRM with one contact, its notes and tags; can be told to fail."""

    def __init__(self) -> None:
        self.notes: list[dict[str, str]] = []
        self.tags: list[str] = []
        self.posts = 0
        self.fail_note_once = False  # the note IS stored, the answer is lost (timeout)
        self.fail_tag_once = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if path == "/contacts/c1" and method == "GET":
            return httpx.Response(
                200, json={"contact": {"id": "c1", "locationId": LOC}}
            )
        if path == "/contacts/other" and method == "GET":
            return httpx.Response(
                200, json={"contact": {"id": "other", "locationId": "x"}}
            )
        if path == "/contacts/c1/notes" and method == "GET":
            return httpx.Response(200, json={"notes": self.notes})
        if path == "/contacts/c1/notes" and method == "POST":
            self.posts += 1
            note = {
                "id": f"n{len(self.notes) + 1}",
                "body": json.loads(request.content)["body"],
            }
            self.notes.append(note)
            if self.fail_note_once:
                self.fail_note_once = False
                raise httpx.ReadTimeout("answer lost")
            return httpx.Response(201, json={"note": note})
        if path == "/contacts/c1/tags" and method == "POST":
            if self.fail_tag_once:
                self.fail_tag_once = False
                return httpx.Response(400, json={})
            self.tags += json.loads(request.content)["tags"]
            return httpx.Response(201, json={})
        return httpx.Response(404)


class FakeRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    async def begin(self, **kw: Any) -> tuple[str, str | None]:
        for rid, r in self.rows.items():  # the same save a moment ago
            if all(
                r[k] == kw[k] for k in ("contact_id", "user_id", "outcome_id", "note")
            ):
                return rid, r["note_id"]
        rid = str(uuid.uuid4())
        self.rows[rid] = {**kw, "note_id": None}
        return rid, None

    async def finish(self, row_id: str, note_id: str) -> None:
        self.rows[row_id]["note_id"] = note_id


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def env(monkeypatch):
    crm, repo = FakeCrm(), FakeRepo()
    monkeypatch.setattr(settings, "GHL_PIT", "pit")
    monkeypatch.setattr(settings, "GHL_SALES_LOCATION_ID", LOC)
    monkeypatch.setattr(ext, "get_outcome_repo", lambda _request: repo)
    monkeypatch.setattr(ghl.asyncio, "sleep", lambda *_a: _noop())
    app.dependency_overrides[require_extension_access] = lambda: USER
    async with httpx.AsyncClient(transport=httpx.MockTransport(crm)) as http:
        app.state.http_client = http
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as client:
            yield client, crm, repo
    app.dependency_overrides.clear()


async def _noop() -> None:
    return None


async def test_saving_an_outcome_adds_one_note_and_one_tag(env):
    client, crm, repo = env
    r = await client.post(
        URL, json={"outcome_id": "send_audit", "note": "Wants the report"}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {
        "note_id": "n1",
        "tag": "call-outcome-send-audit",
        "already_saved": False,
    }
    assert len(crm.notes) == 1 and crm.tags == ["call-outcome-send-audit"]
    body = crm.notes[0]["body"]
    assert body.startswith(
        "Call outcome: Send Audit Report\nWants the report\nSam Rep,"
    )
    assert "[wcm-outcome:" in body
    assert next(iter(repo.rows.values()))["note_id"] == "n1"


async def test_a_repeat_save_a_moment_later_changes_nothing(env):
    client, crm, _ = env
    first = (await client.post(URL, json={"outcome_id": "nurture", "note": "x"})).json()
    again = await client.post(URL, json={"outcome_id": "nurture", "note": "x"})
    assert again.json() == {**first, "already_saved": True}
    assert crm.posts == 1 and len(crm.notes) == 1


async def test_a_lost_answer_is_finished_by_the_retry_without_a_second_note(env):
    """The CRM stored the note, but the answer timed out: the rep sees an error and tries again."""
    client, crm, repo = env
    crm.fail_note_once = True
    first = await client.post(URL, json={"outcome_id": "nurture", "note": "x"})
    assert first.status_code == 502 and crm.posts == 1  # not repeated blindly
    assert next(iter(repo.rows.values()))["note_id"] is None  # not finished
    retry = await client.post(URL, json={"outcome_id": "nurture", "note": "x"})
    assert retry.status_code == 200 and retry.json()["note_id"] == "n1"
    assert crm.posts == 1 and len(crm.notes) == 1  # found the note by its marker
    assert crm.tags == ["call-outcome-nurture"]


async def test_a_failed_tag_is_added_by_the_retry_and_the_note_is_not_doubled(env):
    client, crm, _ = env
    crm.fail_tag_once = True
    assert (
        await client.post(URL, json={"outcome_id": "gatekeeper"})
    ).status_code == 502
    assert crm.tags == [] and len(crm.notes) == 1  # the note went in, the tag did not
    retry = await client.post(URL, json={"outcome_id": "gatekeeper"})
    assert retry.status_code == 200 and crm.tags == ["call-outcome-gatekeeper"]
    assert len(crm.notes) == 1


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"outcome_id": "made_up"}, 422, "unknown_outcome"),
        ({"outcome_id": "nurture", "booked": True}, 422, "booked_not_allowed"),
        ({"outcome_id": ""}, 422, None),
    ],
)
async def test_bad_input_is_refused_before_the_crm_is_touched(env, body, status, code):
    client, crm, repo = env
    r = await client.post(URL, json=body)
    assert r.status_code == status
    if code:
        assert r.json()["error"]["code"] == code
    assert crm.posts == 0 and repo.rows == {}


async def test_a_booking_outcome_may_be_marked_booked(env):
    client, _, repo = env
    r = await client.post(
        URL, json={"outcome_id": "schedule_appointment", "booked": True}
    )
    assert r.status_code == 200
    assert next(iter(repo.rows.values()))["booked"] is True


async def test_a_contact_in_another_location_is_refused(env):
    client, crm, _ = env
    r = await client.post(
        "/api/v1/ext/contacts/other/outcome", json={"outcome_id": "nurture"}
    )
    assert r.status_code == 403 and crm.posts == 0
