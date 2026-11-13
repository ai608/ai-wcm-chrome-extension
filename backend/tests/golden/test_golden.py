"""The Site tab, scored on real clinic sites. A change that makes any score worse fails here.
After an improvement, save the new scores: .venv/bin/python -m tests.golden.score --update"""

import json

from tests.golden import score


def test_site_detection_is_no_worse_than_the_baseline():
    results = {n: score.score(n) for n in score.names()}
    now = score.totals(results)
    baseline = json.loads(score.BASELINE.read_text())
    worse = {k: (baseline[k], now[k]) for k in baseline if now[k] < baseline[k]}
    assert not worse, f"worse than baseline (was, now): {worse}\n{score.table(results)}"
