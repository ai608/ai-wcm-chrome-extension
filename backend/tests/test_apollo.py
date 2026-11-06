import httpx
import pytest

from app.core.config import settings
from app.services import apollo

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_company_maps_apollo_organization(monkeypatch):
    monkeypatch.setattr(settings, "APOLLO_API_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["domain"] == "clinic.com"
        assert request.headers["x-api-key"] == "k"
        return httpx.Response(
            200,
            json={
                "organization": {
                    "name": "Clinic",
                    "short_description": "Primary care and hormone clinic.",
                    "keywords": ["hormone", "primary care"],
                    "annual_revenue_printed": "500K",
                    "phone": "+1(480) 660-8817",
                    "raw_address": "Chandler, AZ, US",
                    "industry": "hospital & health care",
                    "estimated_num_employees": 12,
                    "founded_year": 2015,
                    "linkedin_url": "https://linkedin.com/company/clinic",
                    "technology_names": ["WordPress", "Stripe"],
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        got = await apollo.company(http, "clinic.com")
    assert got == {
        "name": "Clinic",
        "description": "Primary care and hormone clinic.",
        "industry": "hospital & health care",
        "keywords": ["hormone", "primary care"],
        "estimated_revenue": "500K",
        "phone": "+1(480) 660-8817",
        "address": "Chandler, AZ, US",
        "employee_count": 12,
        "linkedin_url": "https://linkedin.com/company/clinic",
        "founded_year": 2015,
        "technologies": ["WordPress", "Stripe"],
    }


async def test_no_match_returns_none():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={}))
    ) as http:
        assert await apollo.company(http, "nobody.com") is None
