import json
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def parse_json_object(text: str) -> dict[str, Any]:
    """The JSON object in a model reply. Some models wrap it in a ```json fence even when
    asked for a JSON object, so strip that; ValueError when there is no object."""
    fenced = _FENCE.match(text)
    out = json.loads(fenced.group(1) if fenced else text)
    if not isinstance(out, dict):
        raise TypeError("not an object")
    return out


async def chat_json(
    http: httpx.AsyncClient,
    system: str,
    user: str,
    *,
    max_tokens: int = 4000,
    model: str | None = None,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """One OpenRouter chat call that must return a JSON object."""
    model = model or settings.SCRIPT_MODEL
    if not settings.OPENROUTER_API_KEY or not model:
        raise AppError(503, "upstream_error", "OPENROUTER_API_KEY/model not set")
    r = await http.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
        json={
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    if r.status_code >= 400:
        raise AppError(502, "upstream_error", f"LLM error {r.status_code}")
    choice = r.json()["choices"][0]
    try:
        return parse_json_object(choice["message"]["content"] or "")
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        reason = (
            "LLM output was cut off"
            if choice.get("finish_reason") == "length"
            else "LLM returned invalid JSON"
        )
        raise AppError(502, "upstream_error", reason) from exc
