import asyncio
import socket

import pytest

from app.core.exceptions import AppError
from app.services import site_audit


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "https://10.0.0.1/",
        "https://example.local/",
        "https://user:pass@example.com/",
        "file:///etc/passwd",
        "https://example.com:8443/",
    ],
)
def test_rejects_unsafe_url(value: str) -> None:
    with pytest.raises(AppError):
        site_audit.normalize_url(value)


@pytest.mark.anyio
async def test_rejects_private_dns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def lookup(*_args: object, **_kwargs: object):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
    with pytest.raises(AppError) as error:
        await site_audit._public_ip("example.com", 443)
    assert error.value.code == "url_not_allowed"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_live_html_analysis_uses_observed_site_data() -> None:
    html = """<!doctype html><html lang="en"><head>
      <title>Wellness Clinic</title><meta name="description" content="Clinic services">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <script type="application/ld+json">{"@type":"MedicalClinic","name":"Wellness Clinic"}</script>
      </head><body><h1>Wellness Clinic</h1>
      <a href="/services/botox">Botox</a><a href="/locations/austin">Austin</a>
      <a href="tel:+15550001234">Call us</a><a href="https://www.instagram.com/example">Instagram</a>
      <img src="/clinic.jpg" alt="Clinic entrance"><form></form></body></html>"""
    result = site_audit.analyze(
        html, "https://clinic.example/", {"name": "Wellness Clinic"}
    )
    assert result["on_page"]["essentials"][0]["value"] == "Wellness Clinic"
    assert result["schema"]["has_local_business"] is True
    assert result["site"]["services"]["clusters"][0]["service"] == "Neurotoxins"
    assert result["convert"]["click_to_call"] is True
    assert result["business"]["gbp"] is None
    assert result["overview"]["provisional"] is True


def test_detects_service_mentioned_on_homepage_without_service_link() -> None:
    result = site_audit.analyze(
        "<html><head><title>Botox and facials</title></head><body><h1>Botox and facials</h1></body></html>",
        "https://clinic.example/",
    )
    names = {item["service"] for item in result["site"]["services"]["clusters"]}
    assert names == {"Neurotoxins", "Chemical Peels & Facials"}


def test_overview_scores_passing_and_failing_checks() -> None:
    html = """<!doctype html><html lang="en"><head><title>Wellness Clinic</title>"""
    html += """<meta name="viewport" content="width=device-width,initial-scale=1">"""
    html += """<link rel="canonical" href="https://clinic.example/"></head>"""
    html += """<body><h1>Wellness Clinic</h1>"""
    html += """<a href="/services/botox">Botox</a><a href="tel:+15550001234">Call</a>"""
    html += """<form></form><img src="/a.jpg" alt="Treatment room"></body></html>"""
    result = site_audit.analyze(html, "https://clinic.example/")
    overview = result["overview"]
    # 8.5/9 fundamentals (meta missing) + 2.5/3 convert (no booking) = 11/12 = 92
    assert overview["score"] == 92
    assert overview["grade"] == "A"
    assert overview["provisional"] is True
    by_key = {c["key"]: c for c in overview["categories"]}
    assert by_key["site_fundamentals"]["score"] == 94
    assert by_key["getting_the_call"]["score"] == 83
    assert overview["issue_count"] == 2
    assert overview["warning_count"] == 2
    titles = [i["title"] for i in overview["top_issues"]]
    assert titles == ["Meta description is missing", "No online booking found"]
    for item in overview["top_issues"]:
        assert "\u2014" not in item["title"] and "\u2014" not in item["detail"]
        assert "needs attention" not in item["title"]
    cluster = result["site"]["services"]["clusters"][0]
    assert cluster["service"] == "Neurotoxins"
    assert cluster["found"] == 1
    assert cluster["expected"] == len(site_audit.SERVICES["Neurotoxins"])
