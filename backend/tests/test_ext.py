import json

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
    {
        "id": "f1",
        "fieldKey": "contact.how_many_locations_do_you_have",
        "dataType": "NUMERICAL",
    },
    {
        "id": "f2",
        "fieldKey": "contact.procedures_offer",
        "dataType": "MULTIPLE_OPTIONS",
    },
    {"id": "r1", "fieldKey": "contact.annual_revenue_", "dataType": "MONETORY"},
    {
        "id": "r2",
        "fieldKey": "contact.annual_revenue",
        "dataType": "SINGLE_OPTIONS",
        "picklistOptions": ["Under $450k", "$450k–$1M", "$1M–$1.5M", "$1.5M +"],
    },
    {"id": "g1", "fieldKey": "contact.google_rating", "dataType": "NUMERICAL"},
    {"id": "g2", "fieldKey": "contact.google_review_count", "dataType": "NUMERICAL"},
    {"id": "site_field", "fieldKey": "contact.your_website_url", "dataType": "TEXT"},
]
CONTACT = {
    "id": "c1",
    "locationId": LOC,
    "firstName": "Maze",
    "customFields": [
        {"id": "f1", "value": 40},
        {"id": "g2", "value": 99},
        {"id": "other", "value": "x"},
    ],
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
    assert body["field_values"]["contact.how_many_locations_do_you_have"] == 40
    assert (await client.get("/api/v1/ext/script")).json()["version"] == ext.SCRIPT[
        "version"
    ]
    assert (await client.get("/api/v1/ext/config")).json()["ghl_location_id"] == LOC


async def test_context_prefills_google_from_research(client, monkeypatch):
    async def fake(*_a):
        return {"contact.google_rating": 4.8, "contact.google_review_count": 191}

    monkeypatch.setattr(ext, "_research_values", fake)
    values = (await client.get("/api/v1/ext/contacts/c1/context")).json()[
        "field_values"
    ]
    assert values["contact.google_rating"] == 4.8  # empty in GHL, filled from research
    assert values["contact.google_review_count"] == 99  # GHL value wins
    body = (await client.get("/api/v1/ext/contacts/c1/context")).json()
    assert body["auto_saved"] == ["contact.google_rating"]
    put = fake_ghl.put.replace(b" ", b"")
    assert b'"field_value":4.8' in put and b"191" not in put


async def test_context_prefills_annual_revenue_from_apollo_and_sets_the_range(
    client, monkeypatch
):
    async def fake(*_a):
        return {"contact.annual_revenue_": 750_000}

    monkeypatch.setattr(ext, "_research_values", fake)
    body = (await client.get("/api/v1/ext/contacts/c1/context")).json()
    assert body["field_values"]["contact.annual_revenue_"] == 750_000
    assert body["auto_saved"] == ["contact.annual_revenue_"]
    put = fake_ghl.put.replace(b" ", b"")
    # the dollar amount and its matching range ("$450k-$1M") are both written
    assert b'"field_value":750000' in put and "$450k–$1M".encode() in put


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
                "contact.how_many_locations_do_you_have": "55",
                "contact.procedures_offer": "Botox",
            }
        },
    )
    assert r.status_code == 200
    assert r.json()["field_values"] == {
        "contact.how_many_locations_do_you_have": 55,
        "contact.procedures_offer": ["Botox"],
    }
    assert b'"field_value":55' in fake_ghl.put.replace(b" ", b"")


async def test_patch_rejects_bad(client):
    r = await client.patch(
        "/api/v1/ext/contacts/c1/fields",
        json={"fields": {"contact.how_many_locations_do_you_have": "abc"}},
    )
    assert r.status_code == 422
    r = await client.patch(
        "/api/v1/ext/contacts/c1/fields", json={"fields": {"nope": 1}}
    )
    assert r.status_code == 422


async def test_revenue_amount_sets_range(client):
    for amount, bucket in [
        (449_999, "Under $450k"),
        (450_000, "$450k–$1M"),
        (1_000_000, "$1M–$1.5M"),
        (2_000_000, "$1.5M +"),
    ]:
        r = await client.patch(
            "/api/v1/ext/contacts/c1/fields",
            json={"fields": {"contact.annual_revenue_": amount}},
        )
        assert r.status_code == 200
        put = json.loads(fake_ghl.put)["customFields"]
        assert {"id": "r2", "field_value": bucket} in put


@pytest.mark.parametrize(
    ("company", "expected"),
    [
        ({"annual_revenue": 2_000_000, "estimated_revenue": "2M"}, 2_000_000),
        (
            {"estimated_revenue": "750K"},
            750_000,
        ),  # audit saved before the number was kept
        ({"estimated_revenue": None}, None),
        (None, None),
    ],
)
async def test_research_values_reads_apollo_revenue_from_the_latest_audit(
    monkeypatch, company, expected
):
    from types import SimpleNamespace

    async def website(_http, _contact):
        return "https://glow.example"

    async def latest(_self, _host):
        return {"business": {"gbp": None, "company": company}}

    monkeypatch.setattr(ext.ghl, "contact_website", website)
    monkeypatch.setattr(ext.AuditRepository, "latest", latest)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(pool=object())))
    got = await ext._research_values(request, None, {})
    assert got.get("contact.annual_revenue_") == expected


async def test_context_prefills_website_url_from_the_contacts_website(
    client, monkeypatch
):
    async def nothing(*_a):
        return {}

    monkeypatch.setattr(ext, "_research_values", nothing)
    # GHL's Website holds a junk path (seen on a real contact); the script wants the site root.
    monkeypatch.setitem(CONTACT, "website", "https://TruHealthClinicUtah.com/.wf_auth")
    body = (await client.get("/api/v1/ext/contacts/c1/context")).json()
    assert (
        body["field_values"]["contact.your_website_url"]
        == "https://truhealthclinicutah.com"
    )
    assert "contact.your_website_url" in body["auto_saved"]
    assert b"https://truhealthclinicutah.com" in fake_ghl.put


async def test_context_keeps_a_website_url_already_in_ghl(client, monkeypatch):
    async def nothing(*_a):
        return {}

    monkeypatch.setattr(ext, "_research_values", nothing)
    monkeypatch.setitem(CONTACT, "website", "https://from-website-field.example")
    monkeypatch.setitem(
        CONTACT,
        "customFields",
        [
            *CONTACT["customFields"],
            {"id": "site_field", "value": "https://typed.example"},
        ],
    )
    body = (await client.get("/api/v1/ext/contacts/c1/context")).json()
    assert body["field_values"]["contact.your_website_url"] == "https://typed.example"
    assert "contact.your_website_url" not in body["auto_saved"]


def test_site_origin_handles_pages_bare_domains_and_junk():
    assert ext._site_origin("https://clinic.com/about/team?x=1") == "https://clinic.com"
    assert ext._site_origin("Clinic.com") == "https://clinic.com"
    assert ext._site_origin("http://clinic.com:8080/a") == "http://clinic.com"
    assert ext._site_origin("ftp://clinic.com") is None
    assert ext._site_origin("  ") is None and ext._site_origin(None) is None
