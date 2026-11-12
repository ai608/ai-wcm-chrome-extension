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


async def test_names_businesses_with_one_call_for_every_answer(monkeypatch):
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
    target = av.build_target(NO_COMPETITORS)
    async with client(lambda _r: reply("x")) as http:
        names = await av.named_businesses(http, {"0": "a", "1": "b"}, target)
    assert len(seen) == 1
    assert names == {
        "0": ["Revive Medical Spa"],
        "1": ["Skin Lab Austin"],
    }  # the clinic is dropped
