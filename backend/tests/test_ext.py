import httpx
import pytest

from app.api.v1 import ext
from app.core.config import settings
from app.core.dependencies import require_extension_access
from app.main import app
from app.services import ghl

pytestmark = pytest.mark.anyio
LOC = "loc1"
CATALOG = [
    {"id": "f1", "fieldKey": "contact.monthly_new_patients", "dataType": "NUMERICAL"},
    {
        "id": "f2",
        "fieldKey": "contact.procedures_offer",
        "dataType": "MULTIPLE_OPTIONS",
    },
    {"id": "site_field", "fieldKey": "contact.your_website_url", "dataType": "TEXT"},
]
CONTACT = {
    "id": "c1",
    "locationId": LOC,
    "firstName": "Maze",
    "customFields": [{"id": "f1", "value": 40}, {"id": "other", "value": "x"}],
}


def fake_ghl(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/customFields"):
        return httpx.Response(200, json={"customFields": CATALOG})
    if request.method == "PUT":
        fake_ghl.put = request.read()  # type: ignore[attr-defined]
        return httpx.Response(200, json={})
    if path == "/contacts/c1":
        return httpx.Response(200, json={"contact": CONTACT})
    if path == "/contacts/other":
        return httpx.Response(200, json={"contact": {**CONTACT, "locationId": "x"}})
    return httpx.Response(404)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setattr(settings, "GHL_PIT", "pit")
    monkeypatch.setattr(settings, "GHL_SALES_LOCATION_ID", LOC)
    monkeypatch.setattr(ghl, "_catalog", None)
    app.dependency_overrides[require_extension_access] = lambda: None
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake_ghl)) as http:
        app.state.http_client = http
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c:
            yield c
    app.dependency_overrides.clear()


async def test_context_and_script(client):
    r = await client.get("/api/v1/ext/contacts/c1/context")
    assert r.status_code == 200
    body = r.json()
    assert body["contact"]["first_name"] == "Maze"
    assert body["field_values"]["contact.monthly_new_patients"] == 40
    assert (await client.get("/api/v1/ext/script")).json()["version"] == ext.SCRIPT[
        "version"
    ]
    assert (await client.get("/api/v1/ext/config")).json()["ghl_location_id"] == LOC


async def test_wrong_location(client):
    r = await client.get("/api/v1/ext/contacts/other/context")
    assert r.status_code == 403 and r.json()["error"]["code"] == "wrong_location"


async def test_research_checks_contact_location_and_website(client):
    missing = await client.get("/api/v1/ext/contacts/c1/research")
    assert missing.status_code == 200
    assert missing.json() == {"audit": None, "reason": "no_website"}
    wrong = await client.get("/api/v1/ext/contacts/other/research")
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "wrong_location"


async def test_research_reads_your_website_url_custom_field(client):
    contact = {
        "customFields": [
            {"id": "site_field", "value": "https://capecoralaesthetics.com"}
        ]
    }
    assert (
        await ghl.contact_website(app.state.http_client, contact)
        == "https://capecoralaesthetics.com"
    )
    assert (
        await ghl.contact_website(
            app.state.http_client, {**contact, "website": "https://native.example"}
        )
        == "https://native.example"
    )


async def test_patch_coerces_and_writes(client):
    r = await client.patch(
        "/api/v1/ext/contacts/c1/fields",
        json={
            "fields": {
                "contact.monthly_new_patients": "55",
                "contact.procedures_offer": "Botox",
            }
        },
    )
    assert r.status_code == 200
    assert r.json()["field_values"] == {
        "contact.monthly_new_patients": 55,
        "contact.procedures_offer": ["Botox"],
    }
    assert b'"field_value":55' in fake_ghl.put.replace(b" ", b"")


async def test_patch_rejects_bad(client):
    r = await client.patch(
        "/api/v1/ext/contacts/c1/fields",
        json={"fields": {"contact.monthly_new_patients": "abc"}},
    )
    assert r.status_code == 422
    r = await client.patch(
        "/api/v1/ext/contacts/c1/fields", json={"fields": {"nope": 1}}
    )
    assert r.status_code == 422
