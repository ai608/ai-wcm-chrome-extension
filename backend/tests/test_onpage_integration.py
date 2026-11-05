from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services import crawl_access, onpage, site_audit, site_crawl

G = "https://glow.example"
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ── robots.txt: Bing and the AI crawlers ──────────────────────────────────────────────────


def judge(robots: str) -> tuple[dict[str, Any], dict[str, str]]:
    groups, _ = crawl_access.parse_robots(robots)
    raw = {
        "state": "ok",
        "groups": groups,
        "declared": True,
        "files": [],
        "urls": [f"{G}/"],
        "truncated": False,
    }
    info, found = crawl_access.judge(raw, f"{G}/", "<html></html>", [f"{G}/"], [])
    return info, dict(found)


def test_a_crawler_singled_out_is_reported_with_the_right_wording():
    info, found = judge("User-agent: Bingbot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    assert found == {"robots_blocks_bing": ""} and info["robots"]["blocked_bots"] == [
        "Bingbot"
    ]
    info, found = judge(
        "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nDisallow: /wp-admin/\n"
    )
    assert found == {"robots_blocks_ai": "GPTBot, ClaudeBot"}
    assert info["robots"]["blocked_bots"] == ["GPTBot", "ClaudeBot"]
    _, found = judge(
        "User-agent: Google-Extended\nUser-agent: PerplexityBot\nUser-agent: OAI-SearchBot\nDisallow: /\n"
    )
    assert found["robots_blocks_ai"] == "OAI-SearchBot, PerplexityBot, Google-Extended"


def test_nobody_is_singled_out_when_everyone_is_welcome_or_everyone_is_blocked():
    assert judge("User-agent: *\nAllow: /\n")[1] == {}
    assert judge("")[1] == {}  # no robots.txt rules: crawlers are free
    assert (
        judge("User-agent: *\nDisallow: /admin/\n")[1] == {}
    )  # a folder is not the whole site
    _, found = judge("User-agent: *\nDisallow: /\n")
    assert "robots_blocks_site" in found  # one clear finding, not four more about bots
    assert not set(found) & {"robots_blocks_bing", "robots_blocks_ai"}


def test_googlebot_welcome_but_everyone_else_blocked_still_flags_bing_and_ai():
    _, found = judge("User-agent: Googlebot\nAllow: /\n\nUser-agent: *\nDisallow: /\n")
    assert set(found) == {"robots_blocks_bing", "robots_blocks_ai"}


# ── PageSpeed: tap targets, zoom, real visitors ───────────────────────────────────────────


def psi(audits: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "lighthouseResult": {
            "categories": {
                k: {"score": 0.9}
                for k in ("performance", "seo", "accessibility", "best-practices")
            },
            "audits": {
                "largest-contentful-paint": {"numericValue": 2000},
                "cumulative-layout-shift": {"numericValue": 0.01},
                **audits,
            },
        },
        **extra,
    }


async def run_psi(body: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=body))
    ) as http:
        settings.GOOGLE_PAGESPEED_API_KEY = "fake"
        return await site_crawl._psi_run(http, f"{G}/", "mobile")


async def test_target_size_and_viewport_audits_become_pass_fail_or_unknown():
    failing = await run_psi(
        psi({"target-size": {"score": 0}, "meta-viewport": {"score": 0}})
    )
    assert failing["tap_targets_ok"] is False and failing["zoom_ok"] is False
    passing = await run_psi(
        psi({"target-size": {"score": 1}, "meta-viewport": {"score": 1}})
    )
    assert passing["tap_targets_ok"] is True and passing["zoom_ok"] is True
    # Lighthouse leaves the audit out, or gives it no score (not applicable): unknown, never "fail"
    unknown = await run_psi(psi({"target-size": {"score": None}}))
    assert unknown["tap_targets_ok"] is None and unknown["zoom_ok"] is None


METRICS = {
    "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 4300, "category": "SLOW"},
    "INTERACTION_TO_NEXT_PAINT": {"percentile": 620, "category": "SLOW"},
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": {
        "percentile": 31,
        "category": "SLOW",
    },  # CrUX sends 0.31 as 31
}


async def test_real_visitor_data_from_the_page_then_from_the_whole_site_then_none():
    url_level = await run_psi(psi({}, loadingExperience={"metrics": METRICS}))
    assert url_level["field"] == {
        "source": "url",
        "lcp_ms": 4300,
        "lcp": "SLOW",
        "inp_ms": 620,
        "inp": "SLOW",
        "cls": 0.31,
        "cls_category": "SLOW",
    }
    origin = await run_psi(
        psi({}, loadingExperience={}, originLoadingExperience={"metrics": METRICS})
    )
    assert origin["field"]["source"] == "origin"
    # a small clinic site: Google has no visits to learn from, as seen on a real audit
    assert (await run_psi(psi({}, loadingExperience={}, originLoadingExperience={})))[
        "field"
    ] is None
    assert (await run_psi(psi({})))["field"] is None


async def test_a_metric_google_did_not_report_stays_empty():
    partial = {"LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 1800, "category": "FAST"}}
    out = await run_psi(psi({}, loadingExperience={"metrics": partial}))
    assert (
        out["field"]["lcp"] == "FAST"
        and out["field"]["inp_ms"] is None
        and out["field"]["cls"] is None
    )


# ── onpage.run with fetched and probes ────────────────────────────────────────────────────

HOME = """<html lang="en"><head><title>Glow Med Spa Austin | Botox and fillers</title>
<meta name="description" content="x"><link rel="canonical" href="https://glow.example/">
<script type="application/ld+json">{"@type": "MedicalClinic", "name": "Glow", "telephone": "+1 512-555-0101",
"address": {"streetAddress": "99 Elm Street"}}</script></head>
<body><h1>Glow Med Spa Austin</h1><a href="/botox">Botox</a><a href="/old">Old</a>
<img src="http://cdn.example/a.jpg" width="1" height="1"><p>Call (512) 555-9999 at 12 Main Street.
Before and after photos prove it.</p></body></html>"""
BOTOX = """<html><head><title>Botox in Austin | Glow</title><meta name="description" content="b">
<link rel="canonical" href="https://glow.example/botox"></head><body><h1>Botox in Austin</h1>
<img src="/a.jpg"><img src="/b.jpg"><img src="/c.jpg"><p>Botox smooths lines.</p></body></html>"""


def run_all(fetched: Any = None, probes: Any = None) -> dict[str, Any]:
    sections = site_audit.analyze(HOME, f"{G}/")
    onpage.run(
        sections,
        f"{G}/",
        {f"{G}/": HOME, f"{G}/botox": BOTOX},
        [f"{G}/", f"{G}/botox"],
        site_crawl.Menu({}, {}, {f"{G}/botox": "botox"}),
        None,
        fetched=fetched,
        probes=probes,
    )
    return sections["on_page"]


def test_run_without_fetched_or_probes_still_runs_the_checks_that_need_neither():
    on = run_all()
    got = {i["key"] for i in on["site_issues"]}
    assert {
        "schema_phone_mismatch",
        "schema_address_mismatch",
        "images_no_dimensions",
        "no_social_tags",
    } <= got
    assert not got & {
        "links_broken",
        "host_split",
        "no_favicon",
        "images_large",
    }  # these need probes
    home = next(p for p in on["pages"] if p["kind"] == "home")
    assert {"mixed_content", "claims_no_disclaimer"} <= {
        i["key"] for i in home["issues"]
    }
    assert on["probes"] == {"ran": False, "checked": 0, "timed_out": 0, "hosts": []}
    assert on["link_check"] == {
        "checked": 0,
        "broken": [],
        "chains": [],
        "redirects": [],
    }
    assert {"deep", "no_booking_link", "no_related_links", "max_depth"} <= set(
        on["structure"]
    )
    assert on["images"]["no_dimensions"] == 3 and "first_image_lazy" in on["images"]


def test_run_with_what_the_reads_and_probes_found():
    fetched = {
        f"{G}/botox": {
            "final": f"{G}/botox",
            "hops": 0,
            "status": 200,
            "x_robots": "noindex",
        },
        f"{G}/gone": {"final": f"{G}/gone", "hops": 0, "status": 404},
    }
    probes = {
        "hosts": [
            {
                "url": "http://glow.example/",
                "status": 200,
                "final": "http://glow.example/",
                "hops": 0,
            },
            {
                "url": "https://glow.example/",
                "status": 200,
                "final": "https://glow.example/",
                "hops": 0,
            },
        ],
        "links": [],
        "images": [{"url": f"{G}/big.jpg", "status": 200, "length": 700_000}],
        "favicon": {"url": f"{G}/favicon.ico", "status": 404},
        "checked": 5,
        "timed_out": 1,
    }
    on = run_all(fetched, probes)
    got = {i["key"] for i in on["site_issues"]}
    assert {
        "links_broken",
        "http_not_redirected",
        "host_split",
        "no_favicon",
        "images_large",
    } <= got
    botox = next(p for p in on["pages"] if p["url"].endswith("/botox"))
    assert "noindex_header" in {i["key"] for i in botox["issues"]}
    assert (
        on["probes"]["ran"]
        and on["probes"]["checked"] == 5
        and on["probes"]["timed_out"] == 1
    )
    assert (
        len(on["probes"]["hosts"]) == 2
        and on["link_check"]["broken"][0]["url"] == f"{G}/gone"
    )
    # every new issue is scored: the summary counts them
    assert on["summary"]["critical"] >= 1 and on["summary"]["score"] < 80


def test_every_issue_key_the_new_checks_can_raise_has_a_catalog_entry_and_plain_wording():
    for table in (onpage.SITE_ISSUES, onpage.ISSUES):
        for key, entry in table.items():
            text = " ".join(str(x) for x in entry)
            assert "—" not in text, f"{key}: no em dashes in owner-facing text"
    from app.services import onpage_more as om

    for key, (sev, title, why) in om.SITE_ISSUES.items():
        assert sev in ("critical", "high", "medium", "low") and title and why
        assert key in onpage.SITE_ISSUES  # run() can raise it
    for key, (hi, lo, title, why) in om.PAGE_ISSUES.items():
        assert (hi or lo) and title and why
        assert om.issue(key, True, f"{G}/p", n=1, detail="x") is not None or hi is None
