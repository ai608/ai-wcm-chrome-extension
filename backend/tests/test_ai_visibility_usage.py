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
