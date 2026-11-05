import asyncio
import json
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services import llm, site_crawl, usage

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def spend(
    model: str = "anthropic/claude-sonnet-5.5", purpose: str = "Page analysis"
) -> None:
    usage.record_ai(
        model,
        purpose,
        tokens=1200,
        prompt_tokens=1000,
        completion_tokens=200,
        cost_micro=45_000,
    )


def test_calls_do_nothing_when_no_audit_is_running():
    usage.record_apify()
    usage.record_firecrawl("scrape")
    spend()  # no meter bound: nothing raises, nothing is kept


async def test_snapshot_adds_up_ai_spend_and_counts_provider_calls():
    async def audit() -> dict[str, Any]:
        meter = usage.bind()
        assert meter.empty()
        spend()
        spend()
        usage.record_ai(
            "google/gemini-2.5-flash-lite",
            "Competitor check",
            tokens=500,
            prompt_tokens=450,
            completion_tokens=50,
            cost_micro=900,
        )
        usage.record_firecrawl("map")
        usage.record_firecrawl("scrape")
        usage.record_firecrawl("scrape")
        usage.record_apify()
        assert not meter.empty()
        return meter.snapshot()

    snap = await asyncio.create_task(audit())
    assert snap["calls"] == 3 and snap["tokens"] == 2900
    assert snap["prompt_tokens"] == 2450 and snap["completion_tokens"] == 450
    assert snap["cost_usd"] == pytest.approx(0.0909)  # OpenRouter only
    by = {line["label"]: line for line in snap["lines"]}
    assert by["Page analysis · claude-sonnet-5.5"]["calls"] == 2
    assert by["Page analysis · claude-sonnet-5.5"]["cost_usd"] == pytest.approx(0.09)
    assert by["Competitor check · gemini-2.5-flash-lite"]["tokens"] == 500
    # Firecrawl and Apify have no dollar figure: counts only, never added to the total
    assert (
        by["Firecrawl"]["calls"] == 3 and by["Firecrawl"]["note"] == "1 map, 2 scrapes"
    )
    assert "cost_usd" not in by["Firecrawl"] and by["Google Maps (Apify)"]["calls"] == 1
    assert isinstance(snap["ms"], int) and snap["ms"] >= 0


async def test_two_audits_never_mix_and_tasks_inside_one_audit_share_its_meter():
    async def audit(n: int) -> dict[str, Any]:
        usage.bind()
        # tasks an audit starts (parallel page reads, PageSpeed) copy the context
        await asyncio.gather(
            *(
                asyncio.create_task(asyncio.sleep(0, usage.record_apify()))
                for _ in range(n)
            )
        )
        await asyncio.sleep(0.01)  # let the other audit run in between
        meter = usage._METER.get()
        assert meter is not None
        return meter.snapshot()

    a, b = await asyncio.gather(
        asyncio.create_task(audit(2)), asyncio.create_task(audit(5))
    )
    assert a["lines"][0]["calls"] == 2 and b["lines"][0]["calls"] == 5


# ── the call sites ────────────────────────────────────────────────────────────────────────


def reply(
    content: str = '{"a": 1}', total: int = 1200, cost: float = 0.045
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {
                "prompt_tokens": total - 200,
                "completion_tokens": 200,
                "total_tokens": total,
                "cost": cost,
            },
        },
    )


async def test_chat_json_records_every_attempt_even_when_the_json_is_unusable(
    monkeypatch,
):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(settings, "SCRIPT_MODEL", "m/script")
    monkeypatch.setattr(llm, "RETRY_DELAY_S", 0)
    # one good call, then a call whose reply is unusable twice (the retry): all three are billed
    bad = reply(content="not json", total=800, cost=0.01)
    replies = iter([reply(), bad, bad])

    async def audit() -> dict[str, Any]:
        meter = usage.bind()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _r: next(replies))
        ) as http:
            await llm.chat_json(http, "s", "u", purpose="Page analysis")
            with pytest.raises(Exception, match="invalid JSON"):
                await llm.chat_json(http, "s", "u", purpose="Page analysis")
        return meter.snapshot()

    snap = await asyncio.create_task(audit())
    line = snap["lines"][0]
    assert line["label"] == "Page analysis · script" and line["calls"] == 3
    assert snap["tokens"] == 2800 and snap["cost_usd"] == pytest.approx(
        0.065
    )  # failed attempts cost money too


async def test_firecrawl_and_apify_calls_are_counted_only_when_they_succeed(
    monkeypatch,
):
    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "k")
    monkeypatch.setattr(settings, "APIFY_API_TOKEN", "t")
    monkeypatch.setattr(settings, "APIFY_GMAPS_ACTOR_ID", "a~b")
    monkeypatch.setattr(settings, "CRAWL_RETRY_DELAY_S", 0)
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        seen.append(path)
        if path.endswith("/map"):
            return httpx.Response(200, json={"links": ["https://glow.example/a"]})
        if path.endswith("/scrape"):
            body = json.loads(req.content)["url"]
            if body.endswith("/out-of-credits"):
                return httpx.Response(402)
            if body.endswith("/flaky") and seen.count(path) == 1:
                return httpx.Response(429)  # one retry, then it works: ONE billed call
            return httpx.Response(200, json={"data": {"rawHtml": "<html>ok</html>"}})
        return httpx.Response(
            200, json=[{"title": "Glow", "website": "https://glow.example"}]
        )

    async def audit() -> dict[str, Any]:
        meter = usage.bind()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await site_crawl.map_site(http, "https://glow.example/")
            assert await site_crawl.scrape(http, "https://glow.example/ok")
            assert await site_crawl.scrape(http, "https://glow.example/flaky")
            assert (
                await site_crawl.scrape(http, "https://glow.example/out-of-credits")
                is None
            )
            await site_crawl.gbp_lookup(http, ["glow med spa"], "glow.example")
        return meter.snapshot()

    snap = await asyncio.create_task(audit())
    by = {line["label"]: line for line in snap["lines"]}
    assert (
        by["Firecrawl"]["calls"] == 3 and by["Firecrawl"]["note"] == "1 map, 2 scrapes"
    )
    assert by["Google Maps (Apify)"]["calls"] == 1
