import asyncio
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.services import usage

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
RETRY_DELAY_S = 2.0
# Worth asking again: the provider was busy or broke for a moment. A 400/401/402/403 will not change.
_TRANSIENT = (408, 429, 500, 502, 503, 504)
LOG_SNIPPET = 200  # characters of a bad reply kept in the log, from each end


def _loads_object(text: str) -> dict[str, Any]:
    out = json.loads(text)
    if not isinstance(out, dict):
        raise TypeError("not an object")
    return out


def parse_json_object(text: str) -> dict[str, Any]:
    """The JSON object in a model reply. Some models wrap it in a ```json fence, add a line of
    prose before or after it, or leave a trailing comma, even when asked for a JSON object.
    Strict parsing goes first; only when it fails is the outermost {...} cut out and a trailing
    comma removed. ValueError when no object can be read."""
    fenced = _FENCE.match(text)
    body = fenced.group(1) if fenced else text
    try:
        return _loads_object(body)
    except ValueError:
        start, end = body.find("{"), body.rfind("}")
        if start < 0 or end <= start:
            raise
        chunk = body[start : end + 1]
        # ponytail: a comma-bracket pair inside a string value would be altered too; rare, and
        # this only runs after strict parsing has already failed.
        for candidate in (chunk, _TRAILING_COMMA.sub(r"\1", chunk)):
            try:
                return _loads_object(candidate)
            except ValueError:
                continue
        raise


async def chat_json(
    http: httpx.AsyncClient,
    system: str,
    user: str,
    *,
    max_tokens: int = 4000,
    model: str | None = None,
    temperature: float = 0.3,
    usage_out: dict[str, Any] | None = None,
    purpose: str = "AI call",
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One OpenRouter chat call that must return a JSON object.

    With `schema` (a JSON Schema) the provider is asked to return exactly that shape, so the
    reply is valid JSON in the expected fields. A provider that refuses the schema (HTTP 400 or
    422; OpenRouter answers 404 "No endpoints found" when no provider accepts every parameter)
    is asked again, once, for plain JSON: the caller must still check what comes back.

    Asked a second time, once, when the provider failed for a moment (timeout, 429, 5xx) or
    the reply was not usable JSON. A reply cut off by `max_tokens` is not asked again: it would
    be cut off again. Every attempt is billed, so every attempt is counted: in the audit's cost
    and, when `usage_out` is given, in it (tokens and cost in micro-USD, summed over attempts)."""
    model = model or settings.SCRIPT_MODEL
    if not settings.OPENROUTER_API_KEY or not model:
        raise AppError(503, "upstream_error", "OPENROUTER_API_KEY/model not set")
    for attempt in (1, 2):
        body_out: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if schema is not None:
            body_out["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            }
            body_out["provider"] = {
                "require_parameters": True
            }  # only providers that obey it
        try:
            r = await http.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                json=body_out,
                timeout=120,
            )
        except httpx.TransportError:  # timeouts and dropped connections
            if attempt == 2:
                raise
            await asyncio.sleep(RETRY_DELAY_S)
            continue
        if r.status_code in _TRANSIENT and attempt == 1:
            wait = r.headers.get("retry-after", "")
            await asyncio.sleep(min(int(wait), 5) if wait.isdigit() else RETRY_DELAY_S)
            continue
        if r.status_code in (400, 404, 422) and schema is not None and attempt == 1:
            logger.warning(
                "llm %s (%s): schema refused (HTTP %d), asking for plain JSON",
                purpose,
                model,
                r.status_code,
            )
            schema = None
            continue
        if r.status_code >= 400:
            raise AppError(502, "upstream_error", f"LLM error {r.status_code}")
        body = r.json()
        choice = body["choices"][0]
        used = body.get("usage") or {}
        spent = {
            "tokens": int(used.get("total_tokens") or 0),
            "prompt_tokens": int(used.get("prompt_tokens") or 0),
            "completion_tokens": int(used.get("completion_tokens") or 0),
            "cost_micro": round(float(used.get("cost") or 0) * 1_000_000),
        }
        if usage_out is not None:
            for k, v in spent.items():
                usage_out[k] = usage_out.get(k, 0) + v
        usage.record_ai(model, purpose, **spent)
        content = (choice.get("message") or {}).get("content") or ""
        try:
            return parse_json_object(content)
        except (ValueError, TypeError) as exc:
            finish = choice.get("finish_reason")
            # What came back, so the next failure explains itself. Model output, never a key.
            logger.warning(
                "llm %s (%s) attempt %d: unusable reply, finish=%s, output_tokens=%d, "
                "head=%r, tail=%r",
                purpose,
                model,
                attempt,
                finish,
                spent["completion_tokens"],
                content[:LOG_SNIPPET],
                content[-LOG_SNIPPET:],
            )
            if finish == "length":
                raise AppError(502, "upstream_error", "LLM output was cut off") from exc
            if attempt == 2:
                raise AppError(
                    502, "upstream_error", "LLM returned invalid JSON"
                ) from exc
            await asyncio.sleep(RETRY_DELAY_S)
    raise AppError(502, "upstream_error", "LLM did not answer")  # unreachable
