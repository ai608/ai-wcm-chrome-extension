import json
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services import ai_visibility as av
from app.services import llm

pytestmark = pytest.mark.anyio

AUDIT: dict[str, Any] = {
    "domain": "glowmedspa.com",
    "business": {"gbp": {"name": "Glow Aesthetics Med Spa"}, "nap": {"name": None}},
    "research": {
        "local_competitors": {
            "state": "ready",
            "data": {
                "items": [
                    {
                        "rank": 1,
                        "name": "Revive Medical Spa",
                        "website": "https://www.revivemedspa.com/",
                        "is_this_business": False,
                    },
                    {
                        "rank": 2,
                        "name": "Glow Aesthetics Med Spa",
                        "website": "https://glowmedspa.com",
                        "is_this_business": True,
                    },
                    {
                        "rank": 3,
                        "name": "Skin Lab Austin",
                        "website": None,
                        "is_this_business": False,
                    },
                ]
            },
        }
    },
}
NO_COMPETITORS = {**AUDIT, "research": {}}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "sk-secret-key")
    monkeypatch.setattr(
        settings,
        "AI_VISIBILITY_MODELS",
        "ChatGPT=openai/gpt-x, Perplexity=perplexity/sonar, bad-pair",
    )
    monkeypatch.setattr(av, "RETRY_DELAY_S", 0)


def reply(text: str, urls: tuple[str, ...] = (), cost: float = 0.001) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": text,
                        "annotations": [
                            {"type": "url_citation", "url_citation": {"url": u}}
                            for u in urls
                        ],
                    }
                }
            ],
            "usage": {"total_tokens": 100, "cost": cost},
        },
    )


def client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def noop_save(_data: dict[str, Any], _cost: int, _tokens: int) -> None:
    return None


# ── matching ──────────────────────────────────────────────────────────────────────────────


def test_engines_parse_and_skip_bad_pairs():
    assert [e.label for e in av.engines()] == ["ChatGPT", "Perplexity"]
    assert av.engines()[1].native_search and not av.engines()[0].native_search


def test_clinic_name_matches_whole_words_and_short_form():
    pats = [av.name_pattern(v) for v in av.name_variants("Glow Aesthetics Med Spa")]
    assert len(pats) == 2  # full name and "Glow Aesthetics"
    short = pats[1]
    assert short and short.search("Try glow  aesthetics, they are great")
    assert not short.search("Glowing Aesthetics Studio")
    assert av.name_variants("Glow Med Spa") == [
        "Glow Med Spa"
    ]  # 1-word short form: too vague


def test_target_uses_local_competitors_and_drops_the_clinic_itself():
    t = av.build_target(AUDIT)
    assert t.source == "local_competitors"
    assert [c.name for c in t.competitors] == ["Revive Medical Spa", "Skin Lab Austin"]
    assert t.competitors[0].host == "revivemedspa.com"
    assert av.build_target(NO_COMPETITORS).source == "none"


def test_read_uses_name_links_and_competitor_websites():
    t = av.build_target(AUDIT)
    a = av.Answer(
        text="See Glow Aesthetics for Botox. Also https://revivemedspa.com/x",
        urls=["https://www.glowmedspa.com/botox", "https://revivemedspa.com/x"],
        tokens=1,
        cost_micro=0,
    )
    s = av.read(a, t)
    assert s["mentioned"] and s["linked"] and s["competitors"] == ["Revive Medical Spa"]
    none = av.read(av.Answer("Try Skin Lab Austin.", [], 1, 0), t)
    assert not none["mentioned"] and not none["linked"]
    assert none["competitors"] == ["Skin Lab Austin"]
    # a look-alike domain is not the clinic's domain
    fake = av.read(av.Answer("x", ["https://notglowmedspa.com/"], 1, 0), t)
    assert fake["linked"] is False


def test_excerpt_is_short_and_centred_on_the_clinic():
    pat = av.name_pattern("Glow Aesthetics")
    text = "word " * 200 + "Glow Aesthetics is great. " + "tail " * 200
    out = av.excerpt(text, pat)
    assert "Glow Aesthetics" in out and len(out) <= av.EXCERPT_CHARS + 2


# ── one call ──────────────────────────────────────────────────────────────────────────────


async def test_web_search_tool_only_for_non_native_engines():
    bodies: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        bodies[body["model"]] = body
        return reply("ok")

    async with client(handler) as http:
        for e in av.engines():
            await av.ask(http, e, "best med spa")
    assert "tools" in bodies["openai/gpt-x"]
    assert "tools" not in bodies["perplexity/sonar"]


async def test_one_retry_on_429_and_error_never_leaks_the_key():
    calls = 0

    def handler(_req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429) if calls == 1 else reply("fine")

    async with client(handler) as http:
        assert (await av.ask(http, av.engines()[0], "q")).text == "fine"

    def always_500(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom sk-secret-key")

    async with client(always_500) as http:
        with pytest.raises(av.AnswerError) as exc:
            await av.ask(http, av.engines()[0], "q")
    assert str(exc.value) == "HTTP 500" and "sk-secret" not in str(exc.value)


# ── whole run ─────────────────────────────────────────────────────────────────────────────


async def test_run_with_local_competitors_makes_no_ai_judge_call(monkeypatch):
    async def forbidden(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise AssertionError("fallback must not run when local competitors exist")

    monkeypatch.setattr(llm, "chat_json", forbidden)

    def handler(req: httpx.Request) -> httpx.Response:
        if json.loads(req.content)["model"].startswith("perplexity"):
            return reply("Go to Skin Lab Austin.")
        return reply(
            "1. Revive Medical Spa 2. Glow Aesthetics",
            ("https://glowmedspa.com/botox",),
        )

    saves: list[tuple[int, int]] = []

    async def save(_d: dict[str, Any], cost: int, tokens: int) -> None:
        saves.append((cost, tokens))

    async with client(handler) as http:
        res = await av.run(
            http, run_id="r1", audit=AUDIT, prompts=["q1", "q2"], save=save
        )
    assert res.status == "ready" and res.error is None
    chat, perp = res.data["engines"]
    assert chat["mentioned"] and chat["linked"] and chat["cited"]
    assert chat["prompts_mentioned"] == chat["prompts_total"] == 2
    assert chat["cited_businesses"] == ["Revive Medical Spa"]
    assert not perp["cited"] and perp["cited_businesses"] == ["Skin Lab Austin"]
    assert res.data["competitors"]["source"] == "local_competitors"
    assert res.data["usage"] == {**res.data["usage"], "calls": 4, "failed": 0}
    assert res.cost_micro == 4000 and res.tokens == 400 and saves
    # one folded log entry per step; each answer keeps its reply for "see full answer"
    assert chat["answers"][0]["text"].startswith("1. Revive")
    ids = [e["id"] for e in res.data["log"]]
    assert (
        len(ids) == len(set(ids)) == 2 + 4 + 2
    )  # prompts, competitors, 4 calls, usage, final
    assert ids[-2:] == ["usage", "final"]  # cost and tokens show before the last step
    assert all(e["status"] != "running" for e in res.data["log"])
    assert len(json.dumps(res.data)) < 6000


async def test_failed_engine_is_reported_and_the_rest_still_count():
    def handler(req: httpx.Request) -> httpx.Response:
        if json.loads(req.content)["model"].startswith("perplexity"):
            return httpx.Response(500)
        return reply("Glow Aesthetics is great")

    async with client(handler) as http:
        res = await av.run(
            http, run_id="r2", audit=AUDIT, prompts=["q1", "q2"], save=noop_save
        )
    assert res.status == "ready"
    perp = res.data["engines"][1]
    assert (
        perp["prompts_failed"] == 2
        and perp["error"] == "HTTP 500"
        and not perp["cited"]
    )
    assert res.data["usage"]["failed"] == 2
    failed = [e for e in res.data["log"] if e["status"] == "failed"]
    assert len(failed) == 2 and failed[0]["detail"]["error"] == "HTTP 500"


async def test_all_engines_failing_marks_the_run_failed():
    async with client(lambda _r: httpx.Response(500)) as http:
        res = await av.run(
            http, run_id="r3", audit=AUDIT, prompts=["q1"], save=noop_save
        )
    assert res.status == "failed" and res.error
    assert res.data["log"][-1]["id"] == "final"


async def test_fallback_names_businesses_with_one_call_when_no_competitor_list(
    monkeypatch,
):
    seen: list[str] = []

    async def fake_chat_json(
        _http: Any, _system: str, user: str, **_k: Any
    ) -> dict[str, Any]:
        seen.append(user)
        return {
            "names": {
                "0": ["Revive Medical Spa", "Glow Aesthetics Med Spa", 5],
                "1": ["Skin Lab Austin"],
                "9": ["Not An Answer"],
            }
        }

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    async with client(lambda _r: reply("Some answer text")) as http:
        res = await av.run(
            http, run_id="r4", audit=NO_COMPETITORS, prompts=["q1"], save=noop_save
        )
    assert len(seen) == 1  # one batched call for every answer
    assert res.data["competitors"]["source"] == "llm"
    chat, perp = res.data["engines"]
    assert chat["cited_businesses"] == [
        "Revive Medical Spa"
    ]  # the clinic itself is dropped
    assert perp["cited_businesses"] == ["Skin Lab Austin"]


async def test_fallback_failure_keeps_the_run_and_logs_it(monkeypatch):
    async def boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm, "chat_json", boom)
    async with client(lambda _r: reply("Glow Aesthetics rocks")) as http:
        res = await av.run(
            http, run_id="r5", audit=NO_COMPETITORS, prompts=["q1"], save=noop_save
        )
    assert res.status == "ready" and res.data["competitors"]["source"] == "none"
    step = next(e for e in res.data["log"] if e["id"] == "competitors")
    assert step["status"] == "failed" and step["detail"]["error"] == "RuntimeError"
