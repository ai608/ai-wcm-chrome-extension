import json
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError


async def chat_json(
    http: httpx.AsyncClient,
    system: str,
    user: str,
    *,
    max_tokens: int = 4000,
    model: str | None = None,
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
            "temperature": 0.3,
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
    try:
        out = json.loads(r.json()["choices"][0]["message"]["content"])
    except (KeyError, IndexError, ValueError) as exc:
        raise AppError(502, "upstream_error", "LLM returned invalid JSON") from exc
    if not isinstance(out, dict):
        raise AppError(502, "upstream_error", "LLM returned invalid JSON")
    return out
