import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

_METER: ContextVar["Meter | None"] = ContextVar("audit_usage_meter", default=None)


@dataclass
class _Ai:
    calls: int = 0
    tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_micro: int = 0


@dataclass
class Meter:
    started: float = field(default_factory=time.monotonic)
    ai: dict[tuple[str, str], _Ai] = field(default_factory=dict)  # (purpose, model)
    firecrawl: dict[str, int] = field(default_factory=dict)  # "map" | "scrape" -> calls
    apify_runs: int = 0

    def empty(self) -> bool:
        return not self.ai and not self.firecrawl and not self.apify_runs

    def ai_totals(self) -> tuple[int, int]:
        """(cost in micro-USD, tokens) of every AI call so far."""
        ai = self.ai.values()
        return sum(a.cost_micro for a in ai), sum(a.tokens for a in ai)

    def snapshot(self) -> dict[str, Any]:
        """The detail of the `usage` log step. `ms` is the whole run, for the step's own time."""
        lines: list[dict[str, Any]] = []
        for (purpose, model), a in self.ai.items():
            lines.append(
                {
                    "kind": "ai",
                    "label": f"{purpose} · {model.rsplit('/', 1)[-1]}",
                    "calls": a.calls,
                    "tokens": a.tokens,
                    "prompt_tokens": a.prompt_tokens,
                    "completion_tokens": a.completion_tokens,
                    "cost_usd": round(a.cost_micro / 1e6, 6),
                }
            )
        fc = sum(self.firecrawl.values())
        if fc:
            parts = [
                f"{n} {k}{'s' if n != 1 else ''}" for k, n in self.firecrawl.items()
            ]
            lines.append(
                {
                    "kind": "firecrawl",
                    "label": "Firecrawl",
                    "calls": fc,
                    "note": ", ".join(parts),
                }
            )
        if self.apify_runs:
            lines.append(
                {
                    "kind": "apify",
                    "label": "Google Maps (Apify)",
                    "calls": self.apify_runs,
                }
            )
        ai = list(self.ai.values())
        return {
            "calls": sum(a.calls for a in ai),
            "tokens": sum(a.tokens for a in ai),
            "prompt_tokens": sum(a.prompt_tokens for a in ai),
            "completion_tokens": sum(a.completion_tokens for a in ai),
            "cost_usd": round(sum(a.cost_micro for a in ai) / 1e6, 6),
            "lines": lines,
            "ms": round((time.monotonic() - self.started) * 1000),
        }


def bind() -> Meter:
    """Start metering the current audit (and every task it starts from here on)."""
    meter = Meter()
    _METER.set(meter)
    return meter


def record_ai(
    model: str,
    purpose: str,
    *,
    tokens: int,
    prompt_tokens: int,
    completion_tokens: int,
    cost_micro: int,
) -> None:
    if (meter := _METER.get()) is None:
        return
    a = meter.ai.setdefault((purpose, model), _Ai())
    a.calls += 1
    a.tokens += tokens
    a.prompt_tokens += prompt_tokens
    a.completion_tokens += completion_tokens
    a.cost_micro += cost_micro


def record_firecrawl(kind: str) -> None:
    if (meter := _METER.get()) is not None:
        meter.firecrawl[kind] = meter.firecrawl.get(kind, 0) + 1


def record_apify() -> None:
    if (meter := _METER.get()) is not None:
        meter.apify_runs += 1
