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
                        "name": "Revive Medical Spa",
                        "website": None,
                        "is_this_business": False,
                    }
                ]
            },
        }
    },
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "sk-secret")
    monkeypatch.setattr(
        settings, "AI_VISIBILITY_MODELS", "ChatGPT=openai/x, Claude=anthropic/y"
    )
    monkeypatch.setattr(av, "RETRY_DELAY_S", 0)


# model -> (prompt tokens, completion tokens, cost in USD) for ONE call
PRICES = {"openai/x": (1000, 200, 0.0030), "anthropic/y": (2000, 400, 0.0125)}


def handler(req: httpx.Request) -> httpx.Response:
    p, c, cost = PRICES[json.loads(req.content)["model"]]
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "Try Revive Medical Spa."}}],
            "usage": {
                "prompt_tokens": p,
                "completion_tokens": c,
                "total_tokens": p + c,
                "cost": cost,
            },
        },
    )


async def save(_d: dict[str, Any], _c: int, _t: int) -> None:
    return None


def step(res: av.Result, step_id: str) -> dict[str, Any]:
    return next(e for e in res.data["log"] if e["id"] == step_id)


async def test_usage_step_has_totals_split_and_per_engine_numbers():
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        res = await av.run(
            http, run_id="u1", audit=AUDIT, prompts=["q1", "q2"], save=save
        )
    u = step(res, "usage")["detail"]
    # 2 questions x 2 engines: ChatGPT 2 x (1000+200), Claude 2 x (2000+400)
    assert u["calls"] == 4 and u["failed"] == 0
    assert (
        u["prompt_tokens"] == 6000
        and u["completion_tokens"] == 1200
        and u["tokens"] == 7200
    )
    assert u["cost_usd"] == pytest.approx(2 * 0.0030 + 2 * 0.0125)
    by = {e["engine"]: e for e in u["by_engine"]}
    assert by["ChatGPT"] == {
        "engine": "ChatGPT",
        "calls": 2,
        "tokens": 2400,
        "prompt_tokens": 2000,
        "completion_tokens": 400,
        "cost_usd": pytest.approx(0.006),
    }
    assert by["Claude"]["tokens"] == 4800 and by["Claude"]["cost_usd"] == pytest.approx(
        0.025
    )
    assert "judge" not in u  # competitors came from Google Maps: no judge call
    # the run totals saved to the database are the same numbers
    assert res.tokens == 7200 and res.cost_micro == 31_000
    assert res.data["usage"]["cost_usd"] == pytest.approx(0.031)


async def test_usage_step_comes_right_before_the_final_step_and_carries_the_run_time():
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        res = await av.run(http, run_id="u2", audit=AUDIT, prompts=["q1"], save=save)
    ids = [e["id"] for e in res.data["log"]]
    assert ids[-2:] == ["usage", "final"]
    e = step(res, "usage")
    assert e["status"] == "done" and e["label"] == "Cost and tokens"
    assert isinstance(e["ms"], int) and e["ms"] >= 0  # whole-run time for the row


async def test_total_equals_the_sum_of_the_per_call_lines():
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        res = await av.run(
            http, run_id="u3", audit=AUDIT, prompts=["q1", "q2"], save=save
        )
    per_call = sum(
        e["detail"]["cost_usd"] for e in res.data["log"] if e["id"].startswith("ask:")
    )
    assert step(res, "usage")["detail"]["cost_usd"] == pytest.approx(per_call)


async def test_judge_call_is_counted_in_totals_and_shown_separately(monkeypatch):
    async def fake_chat_json(
        _http: Any,
        _s: str,
        _u: str,
        *,
        usage_out: dict[str, Any] | None = None,
        **_k: Any,
    ) -> dict[str, Any]:
        assert usage_out is not None
        usage_out.update(
            tokens=500, prompt_tokens=450, completion_tokens=50, cost_micro=900
        )
        return {"names": {"0": ["Skin Lab Austin"]}}

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    no_list = {**AUDIT, "research": {}}  # no Google Maps competitors: the judge runs
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        res = await av.run(http, run_id="u4", audit=no_list, prompts=["q1"], save=save)
    u = step(res, "usage")["detail"]
    assert u["judge"] == {"tokens": 500, "cost_usd": pytest.approx(0.0009)}
    assert u["tokens"] == 3600 + 500 and u["prompt_tokens"] == 3000 + 450
    assert u["cost_usd"] == pytest.approx(0.0155 + 0.0009)
    assert res.cost_micro == 15_500 + 900  # the daily budget sees the judge spend too


async def test_failed_run_still_logs_a_usage_step_with_nothing_spent():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _r: httpx.Response(500))
    ) as http:
        res = await av.run(http, run_id="u5", audit=AUDIT, prompts=["q1"], save=save)
    assert res.status == "failed"
    ids = [e["id"] for e in res.data["log"]]
    assert ids[-2:] == ["usage", "final"]
    u = step(res, "usage")["detail"]
    assert u["failed"] == 2 and u["tokens"] == 0 and u["cost_usd"] == 0


async def test_chat_json_reports_usage_only_when_asked(monkeypatch):
    monkeypatch.setattr(settings, "SCRIPT_MODEL", "m/x")

    def ok(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"a": 1}'}}],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 3,
                    "total_tokens": 10,
                    "cost": 0.0002,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as http:
        assert await llm.chat_json(http, "s", "u") == {"a": 1}  # old callers: unchanged
        used: dict[str, Any] = {}
        await llm.chat_json(http, "s", "u", usage_out=used)
    assert used == {
        "tokens": 10,
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "cost_micro": 200,
    }
