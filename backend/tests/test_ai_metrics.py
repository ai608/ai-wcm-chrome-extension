"""The scoring maths must equal the POC's. `data/ai_metrics_parity.json` was made by running the
POC's own metrics.py (pandas) on the same rows; here the pure-Python port must give the same."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.services import ai_metrics as m

DATA = json.loads(
    (Path(__file__).parent / "data" / "ai_metrics_parity.json").read_text()
)


def close(a: Any, b: Any) -> None:
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), (set(a), set(b))
        for k in a:
            close(a[k], b[k])
    elif isinstance(a, list):
        assert len(a) == len(b)
        for x, y in zip(a, b, strict=True):
            close(x, y)
    elif isinstance(a, float | int) and not isinstance(a, bool):
        assert b == pytest.approx(a, abs=1e-9)
    else:
        assert a == b


def test_port_gives_the_same_numbers_as_the_poc():
    got = m.compute(
        DATA["rows"],
        "Glow",
        DATA["brands"],
        DATA["prompt_weights"],
        DATA["engine_weights"],
    )
    want = DATA["expected"]
    by_prompt = lambda xs: {x["prompt_id"]: x for x in xs}
    close(
        by_prompt(want.pop("prompt_analytics")), by_prompt(got.pop("prompt_analytics"))
    )
    # the POC omits this key; ours is always present
    want.pop("prompt_category_breakdown", None)
    close(want, got)


def test_not_mentioned_scores_zero_and_a_citation_alone_does_not_count():
    row = {
        "prompt_id": "p",
        "engine": "E",
        "run": 1,
        "brand": "A",
        "mentioned": False,
        "occurrences": 0,
        "list_rank": None,
        "first_position": None,
        "cited": True,
        "sentiment": 1.0,
    }
    out = m.compute([row], "A", ["A"])
    assert out["visibility_index"] == 0 and out["coverage"] == 0


def test_no_rows_gives_an_empty_blob_not_a_crash():
    assert m.compute([], "A", ["A", "B"])["visibility_index"] == 0


def test_wilson_range_is_wide_for_few_answers_and_tight_for_many():
    lo1, hi1 = m.wilson_interval(2, 4)
    lo2, hi2 = m.wilson_interval(200, 400)
    assert (hi1 - lo1) > 3 * (hi2 - lo2)
    assert m.wilson_interval(0, 0) == (0.0, 0.0)


def test_mention_rate_reads_only_the_target():
    rows = [
        {"brand": "A", "mentioned": True},
        {"brand": "A", "mentioned": False},
        {"brand": "B", "mentioned": True},
    ]
    out = m.mention_rate(rows, "A")
    assert (out["k"], out["n"], out["rate"]) == (1, 2, 0.5)
    assert out["low"] < 0.5 < out["high"]
