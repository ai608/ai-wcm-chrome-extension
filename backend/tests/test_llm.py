import asyncio
import logging
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import AppError
from app.services import llm, usage

pytestmark = pytest.mark.anyio

SECRET = "sk-or-v1-supersecretkeymaterial"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SECRET)
    monkeypatch.setattr(settings, "SCRIPT_MODEL", "m/x")
    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    return slept


def reply(
    content: str, finish: str = "stop", out: int = 200, cost: float = 0.05
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": out,
                "total_tokens": 1000 + out,
                "cost": cost,
            },
        },
    )


class Script:
    """A fake OpenRouter that answers from a list and counts the calls."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, _req: httpx.Request) -> httpx.Response:
        self.calls += 1
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


async def run(script: Script, **kw: Any) -> dict[str, Any]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(script)) as http:
        return await llm.chat_json(http, "s", "u", **kw)


# ── reading the reply ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1, "b": [1, 2]}',
        '```json\n{"a": 1, "b": [1, 2]}\n```',
        'Here is the JSON you asked for:\n{"a": 1, "b": [1, 2]}\nHope that helps!',
        '{"a": 1, "b": [1, 2,],}',  # trailing commas
        '```json\n{"a": 1, "b": [1, 2,]}\n```\nNote: b is a list.',
    ],
)
def test_parse_reads_the_object_through_fences_prose_and_trailing_commas(text):
    assert llm.parse_json_object(text) == {"a": 1, "b": [1, 2]}


def test_parse_keeps_braces_inside_strings_and_nested_objects():
    text = 'Sure! {"note": "use {curly} braces", "n": {"deep": {"x": 1}}} done'
    assert llm.parse_json_object(text) == {
        "note": "use {curly} braces",
        "n": {"deep": {"x": 1}},
    }


@pytest.mark.parametrize(
    "text", ["", "no json here", '{"a": 1', '{"a": }', "[1, 2, 3]", '"text"']
)
def test_parse_still_refuses_what_is_not_an_object(text):
    with pytest.raises((ValueError, TypeError)):
        llm.parse_json_object(text)


async def test_prose_around_the_json_is_read_without_asking_again():
    s = Script(reply('Here you go: {"ok": true}'))
    assert await run(s) == {"ok": True} and s.calls == 1


# ── asking again ──────────────────────────────────────────────────────────────────────────


async def test_unusable_reply_is_asked_again_once_and_both_attempts_are_counted():
    s = Script(
        reply("I could not produce JSON, sorry", cost=0.12),
        reply('{"ok": 1}', cost=0.11),
    )
    used: dict[str, Any] = {}

    async def audit() -> tuple[dict[str, Any], dict[str, Any]]:
        meter = usage.bind()
        out = await run(s, usage_out=used, purpose="Page analysis")
        return out, meter.snapshot()

    out, snap = await asyncio.create_task(audit())
    assert out == {"ok": 1} and s.calls == 2
    assert (
        used["cost_micro"] == 230_000 and used["tokens"] == 2400
    )  # summed over both attempts
    assert snap["lines"][0]["calls"] == 2 and snap["cost_usd"] == pytest.approx(0.23)


async def test_two_unusable_replies_fail_after_exactly_two_calls_and_log_what_came_back(
    caplog,
):
    s = Script(reply('{"a": [1, 2', out=77), reply("not json at all", out=88))
    with (
        caplog.at_level(logging.WARNING, logger="app.services.llm"),
        pytest.raises(AppError) as exc,
    ):
        await run(s, purpose="Page analysis")
    assert exc.value.message == "LLM returned invalid JSON" and s.calls == 2
    warnings = [
        r.getMessage() for r in caplog.records if "unusable reply" in r.getMessage()
    ]
    assert len(warnings) == 2
    assert (
        "attempt 1" in warnings[0]
        and "finish=stop" in warnings[0]
        and "output_tokens=77" in warnings[0]
    )
    assert "'{\"a\": [1, 2'" in warnings[0] and "not json at all" in warnings[1]
    assert SECRET not in caplog.text


async def test_a_reply_cut_off_by_the_token_limit_is_not_asked_again():
    s = Script(reply('{"a": [1, 2', finish="length", out=16000))
    with pytest.raises(AppError) as exc:
        await run(s)
    assert exc.value.message == "LLM output was cut off" and s.calls == 1


async def test_a_busy_provider_is_asked_again_once_and_retry_after_is_honoured(
    _configured,
):
    s = Script(httpx.Response(429, headers={"retry-after": "3"}), reply('{"ok": 1}'))
    assert await run(s) == {"ok": 1} and s.calls == 2
    assert _configured == [3]
    s = Script(httpx.Response(503), httpx.Response(503))
    with pytest.raises(AppError) as exc:
        await run(s)
    assert exc.value.message == "LLM error 503" and s.calls == 2


async def test_a_long_retry_after_is_capped_and_a_bad_request_is_never_repeated(
    _configured,
):
    s = Script(httpx.Response(429, headers={"retry-after": "90"}), reply('{"ok": 1}'))
    await run(s)
    assert _configured == [5]
    for status in (400, 401, 402, 403):
        s = Script(httpx.Response(status))
        with pytest.raises(AppError, match=f"LLM error {status}"):
            await run(s)
        assert s.calls == 1


async def test_a_timeout_is_asked_again_once_then_it_raises():
    s = Script(httpx.ReadTimeout("slow"), reply('{"ok": 1}'))
    assert await run(s) == {"ok": 1} and s.calls == 2
    s = Script(httpx.ReadTimeout("slow"), httpx.ConnectError("down"))
    with pytest.raises(httpx.TransportError):
        await run(s)
    assert s.calls == 2


async def test_no_key_makes_no_call():
    settings.OPENROUTER_API_KEY = ""
    s = Script()
    with pytest.raises(AppError, match="not set"):
        await run(s)
    assert s.calls == 0


@pytest.mark.parametrize("status", [400, 404, 422])
async def test_refused_schema_is_asked_again_as_plain_json(status: int) -> None:
    """OpenRouter answers 404 "No endpoints found" when no provider takes every parameter."""
    bodies: list[dict[str, Any]] = []

    def answer(req: httpx.Request) -> httpx.Response:
        bodies.append(__import__("json").loads(req.content))
        return httpx.Response(status) if len(bodies) == 1 else reply('{"a": 1}')

    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        out = await llm.chat_json(http, "s", "u", schema=schema)
    assert out == {"a": 1}
    assert bodies[0]["response_format"]["type"] == "json_schema"
    assert "provider" in bodies[0]
    assert bodies[1]["response_format"] == {"type": "json_object"}
    assert "provider" not in bodies[1]
