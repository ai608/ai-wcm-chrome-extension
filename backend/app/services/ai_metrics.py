"""Scores for the full AI visibility report. Pure functions: no I/O, no pandas.

Ported from the POC's `metrics.py` (same maths, proven equal in tests/test_ai_metrics.py).

One input row = one brand in one answer:
    prompt_id, engine, run, brand, mentioned, occurrences, list_rank, first_position, cited,
    sentiment (-1..1)

Score of one brand in one answer (0 when it is not mentioned):
    cell = 0.60 x prominence + 0.25 x cited + 0.15 x sentiment
    prominence = 0.50 x (1 - first_position) + 0.30 x 1/log2(rank + 1) + 0.20 x min(1, mentions/3)
These weights are choices, not laws. They are versioned (SCORING_VERSION): change a weight, bump
the version, and old reports stay readable.
"""

from collections import defaultdict
from collections.abc import Iterable
from math import log2, sqrt
from typing import Any

SCORING_VERSION = 1
PROMINENCE = (0.50, 0.30, 0.20)  # order in the text, list rank, how often
CELL = (0.60, 0.25, 0.15)  # prominence, linked to the brand's site, sentiment
N_REF = 3  # this many mentions in one answer is "often enough"

Row = dict[str, Any]


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def prominence(first_pos: float | None, list_rank: int | None, occ: int) -> float:
    """How prominent a brand is inside one answer, 0..1."""
    a, b, c = PROMINENCE
    order = 1.0 - (first_pos if first_pos is not None else 1.0)
    rank = (1.0 / log2(list_rank + 1)) if list_rank and list_rank > 0 else order
    freq = min(1.0, (occ or 0) / N_REF)
    return _clip(a * order + b * rank + c * freq)


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% range for the true mention probability when k of n answers named the brand."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _avg(values: list[float], weights: list[float]) -> float:
    total = sum(weights)
    return (
        sum(v * w for v, w in zip(values, weights, strict=True)) / total
        if total
        else 0.0
    )


def _cell_run(r: Row) -> tuple[float, float, float]:
    """(cell score, cited, sentiment) for one row."""
    if not r["mentioned"]:
        return 0.0, float(bool(r.get("cited"))), float(r.get("sentiment") or 0.0)
    alpha, beta, gamma = CELL
    phi = prominence(
        r.get("first_position"), r.get("list_rank"), int(r.get("occurrences") or 0)
    )
    cited = float(bool(r.get("cited")))
    sent = _clip(float(r.get("sentiment") or 0.0), -1.0, 1.0)
    psi = (sent + 1.0) / 2.0
    return alpha * phi + beta * cited + gamma * psi, cited, sent


def _empty(target: str, brands: list[str]) -> dict[str, Any]:
    return {
        "target": target,
        "visibility_index": 0,
        "share_of_voice": {},
        "per_brand": {},
        "matrix": {},
        "confidence_intervals": {},
        "leaderboard": brands,
        "gap_vs_top_competitor": 0,
        "per_model": {},
        "coverage": 0,
        "citation_rate": 0,
        "sentiment_index": 0,
        "sentiment_breakdown": {"positive": 0.0, "neutral": 0.0, "negative": 0.0},
        "prompt_analytics": [],
    }


def compute(
    rows: Iterable[Row],
    target: str,
    brands: list[str],
    prompt_weights: dict[Any, float] | None = None,
    engine_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """All scores from raw rows. `brands` must contain `target`."""
    rows = list(rows)
    if not rows:
        return _empty(target, brands)
    pw, ew = prompt_weights or {}, engine_weights or {}

    # Cell = one brand x prompt x engine, averaged over the repeats.
    groups: dict[tuple[str, Any, str], list[Row]] = defaultdict(list)
    scored: dict[int, tuple[float, float, float]] = {}
    for r in rows:
        groups[(r["brand"], r["prompt_id"], r["engine"])].append(r)
        scored[id(r)] = _cell_run(r)
    cells: dict[tuple[str, Any, str], dict[str, float]] = {}
    for key, grp in groups.items():
        n = len(grp)
        cells[key] = {
            "V": sum(scored[id(r)][0] for r in grp) / n,
            "pi": sum(1.0 for r in grp if r["mentioned"]) / n,
            "pi_cite": sum(scored[id(r)][1] for r in grp) / n,
            "mentions": float(sum(1 for r in grp if r["mentioned"])),
            "runs": float(n),
        }

    per_brand: dict[str, dict[str, Any]] = {}
    for brand in brands:
        mine = {k: v for k, v in cells.items() if k[0] == brand}
        if not mine:
            per_brand[brand] = {
                "VI": 0.0,
                "per_model": {},
                "coverage": 0.0,
                "citation_rate": 0.0,
                "sentiment": 0.0,
            }
            continue
        by_engine: dict[str, list[tuple[Any, dict[str, float]]]] = defaultdict(list)
        for (_, prompt, engine), cell in mine.items():
            by_engine[engine].append((prompt, cell))
        vm = {
            e: _avg([c["V"] for _, c in items], [float(pw.get(p, 1)) for p, _ in items])
            for e, items in by_engine.items()
        }
        vi = 100.0 * _avg(list(vm.values()), [float(ew.get(e, 1.0)) for e in vm])
        prompts = {k[1] for k in mine}
        coverage = len({k[1] for k, v in mine.items() if v["pi"] > 0}) / max(
            len(prompts), 1
        )
        wv = [float(pw.get(k[1], 1)) * float(ew.get(k[2], 1.0)) for k in mine]
        cite = _avg([v["pi_cite"] for v in mine.values()], wv)
        sents = [
            scored[id(r)][2] for r in rows if r["brand"] == brand and r["mentioned"]
        ]
        per_brand[brand] = {
            "VI": round(vi, 1),
            "per_model": {k: round(v, 4) for k, v in vm.items()},
            "coverage": round(coverage, 3),
            "citation_rate": round(cite, 3),
            "sentiment": round(sum(sents) / len(sents), 2) if sents else 0.0,
        }

    # Share of voice: in each prompt x engine, this brand's share of all tracked brands' mentions.
    slots = {(k[1], k[2]) for k in cells}
    sov_sum: dict[str, float] = dict.fromkeys(brands, 0.0)
    for slot in slots:
        pis = {b: cells.get((b, slot[0], slot[1]), {}).get("pi", 0.0) for b in brands}
        total = sum(pis.values())
        if total:
            for b in brands:
                sov_sum[b] += pis[b] / total
    sov = {b: round(sov_sum[b] / len(slots), 3) for b in brands}

    matrix: dict[str, dict[str, float]] = defaultdict(dict)
    ci: dict[str, dict[str, float]] = {}
    for (brand, prompt, engine), cell in cells.items():
        if brand != target:
            continue
        matrix[engine][str(prompt)] = round(cell["V"], 3)
        lo, hi = wilson_interval(int(cell["mentions"]), int(cell["runs"]))
        ci[f"{prompt}_{engine}"] = {
            "low": round(lo, 3),
            "high": round(hi, 3),
            "pi": round(cell["pi"], 3),
        }

    leaderboard = sorted(brands, key=lambda b: per_brand[b]["VI"], reverse=True)
    rivals = [per_brand[b]["VI"] for b in brands if b != target]
    gap = per_brand[target]["VI"] - max(rivals) if rivals else 0.0

    mentioned = [
        scored[id(r)][2] for r in rows if r["brand"] == target and r["mentioned"]
    ]
    n = len(mentioned)
    breakdown = {
        "positive": round(sum(1 for s in mentioned if s > 0.2) / n, 3) if n else 0.0,
        "neutral": round(sum(1 for s in mentioned if -0.2 <= s <= 0.2) / n, 3)
        if n
        else 0.0,
        "negative": round(sum(1 for s in mentioned if s < -0.2) / n, 3) if n else 0.0,
    }

    analytics: list[dict[str, Any]] = []
    for prompt in dict.fromkeys(k[1] for k in cells if k[0] == target):
        mine_p = {
            k[2]: v for k, v in cells.items() if k[0] == target and k[1] == prompt
        }
        analytics.append(
            {
                "prompt_id": prompt,
                "per_model": {e: round(c["V"], 3) for e, c in mine_p.items()},
                "avg_visibility": round(
                    sum(c["V"] for c in mine_p.values()) / len(mine_p), 3
                ),
                "mention_rate": round(
                    sum(c["pi"] for c in mine_p.values()) / len(mine_p), 3
                ),
            }
        )

    t = per_brand[target]
    return {
        "target": target,
        "visibility_index": t["VI"],
        "share_of_voice": sov,
        "per_brand": per_brand,
        "matrix": dict(matrix),
        "confidence_intervals": ci,
        "leaderboard": leaderboard,
        "gap_vs_top_competitor": round(gap, 1),
        "per_model": t["per_model"],
        "coverage": t["coverage"],
        "citation_rate": t["citation_rate"],
        "sentiment_index": t["sentiment"],
        "sentiment_breakdown": breakdown,
        "prompt_analytics": analytics,
    }


def mention_rate(rows: Iterable[Row], target: str) -> dict[str, Any]:
    """The plain number to show next to the score: "named in k of n answers", with its range."""
    mine = [r for r in rows if r["brand"] == target]
    k, n = sum(1 for r in mine if r["mentioned"]), len(mine)
    lo, hi = wilson_interval(k, n)
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, 3) if n else 0.0,
        "low": round(lo, 3),
        "high": round(hi, 3),
    }
