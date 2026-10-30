import asyncio
import socket

import pytest

from app.core.exceptions import AppError
from app.services import site_audit, site_score


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
    # the home page step no longer scores: site_score.compute runs after the whole audit
    assert overview["score"] is None and overview["grade"] is None
    assert overview["provisional"] is True
    assert overview["categories"] == [] and overview["top_issues"] == []
    final = site_score.compute(result)
    by_key = {c["key"]: c for c in final["categories"]}
    # 8.5/9 essentials (meta missing) and half the schema points; no PageSpeed
    assert by_key["site_fundamentals"]["score"] == 86
    titles = [i["title"] for i in final["top_issues"]]
    assert "Meta description is missing" not in titles[:3]
    assert "No online booking found" in titles
    for item in final["top_issues"]:
        assert "\u2014" not in item["title"] and "\u2014" not in item["detail"]
        assert "needs attention" not in item["title"]
    cluster = result["site"]["services"]["clusters"][0]
    assert cluster["service"] == "Neurotoxins"
    assert cluster["found"] == 1
    assert cluster["expected"] == len(site_audit.SERVICES["Neurotoxins"])


@pytest.mark.anyio
async def test_fetch_html_retries_a_passing_failure_once_but_not_a_final_one(
    monkeypatch,
):
    from app.core.exceptions import AppError

    monkeypatch.setattr(site_audit.settings, "CRAWL_RETRY_DELAY_S", 0)
    calls = []

    def once(results):
        seq = iter(results)

        async def fake(url, accept=("text/html",)):
            calls.append(url)
            r = next(seq)
            if isinstance(r, Exception):
                raise r
            return r

        return fake

    transient = site_audit.TransientFetchError("down")
    final = AppError(422, "site_unreachable", "Website could not be fetched")
    monkeypatch.setattr(site_audit, "_fetch_once", once([transient, ("<html>", "u")]))
    assert await site_audit.fetch_html("https://a.example/") == ("<html>", "u")
    assert len(calls) == 2
    calls.clear()
    monkeypatch.setattr(site_audit, "_fetch_once", once([final, ("<html>", "u")]))
    with pytest.raises(AppError):  # a 403/404 is not retried
        await site_audit.fetch_html("https://a.example/")
    assert len(calls) == 1
    calls.clear()
    monkeypatch.setattr(
        site_audit, "_fetch_once", once([transient, transient, ("x", "u")])
    )
    with pytest.raises(AppError):  # one retry only
        await site_audit.fetch_html("https://a.example/")
    assert len(calls) == 2
