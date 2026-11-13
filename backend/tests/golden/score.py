"""Score the Site tab on the saved clinic sites against hand-written answers.

    .venv/bin/python -m tests.golden.score            # print the table
    .venv/bin/python -m tests.golden.score --update   # also save it as the new baseline

Runs offline: the same code an audit runs on its crawl (site_facts), without the AI step.
Pages are compared by path, so http/https and www do not matter. Pages in `ignore` count
neither for nor against (hubs, shop pages, pages nobody could label from their title).
"""

import gzip
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.services import audit_runner, page_types, site_ai, site_audit, site_crawl

HERE = Path(__file__).parent
BASELINE = HERE / "baseline.json"


def path(url: str) -> str:
    return urlsplit(url).path.rstrip("/").lower() or "/"


def names() -> list[str]:
    return sorted(
        p.name.removesuffix(".expected.json") for p in HERE.glob("*.expected.json")
    )


def run(name: str, schema: bool = True, ai: bool = True) -> dict[str, Any]:
    """The Site sections for one saved site, as an audit builds them. The AI's page types are
    replayed from <name>.ai.json (recorded once with --record-ai); the AI is never called."""
    d = json.loads(gzip.decompress((HERE / f"{name}.json.gz").read_bytes()))
    home, final = d["home_html"], d["final_url"]
    sections = site_audit.analyze(home, final)
    menu = site_crawl.nav_links(home, final)
    if not schema:
        site_crawl.enrich(sections, d["urls"], d["pages"], None, menu)
        return sections
    lists = audit_runner.site_facts(sections, home, d["urls"], d["pages"], None, menu)
    if lists["areas"]:
        site_ai.apply_areas(
            sections, lists["areas"], {final: home, **d["pages"]}, d["urls"]
        )
    recorded = HERE / f"{name}.ai.json"
    if ai and recorded.exists():
        labels = json.loads(recorded.read_text())["labels"]
        page_types.apply(sections, labels, d["pages"])
    return sections


async def record_ai(name: str) -> int:
    """Ask the AI once for this site's uncertain pages and save its answers for replay."""
    import httpx

    d = json.loads(gzip.decompress((HERE / f"{name}.json.gz").read_bytes()))
    sections = run(name, ai=False)
    menu = site_crawl.nav_links(d["home_html"], d["final_url"])
    urls = page_types.candidates(sections, d["urls"], d["pages"], menu)
    async with httpx.AsyncClient(timeout=60) as http:
        labels = await page_types.read_types(http, urls, d["pages"])
    record = {
        "prompt_version": page_types.PROMPT_VERSION,
        "model": page_types.settings.RESEARCH_MODEL,
        "labels": labels,
    }
    (HERE / f"{name}.ai.json").write_text(json.dumps(record, indent=2) + "\n")
    return len(labels)


def _counts(got: set[str], want: set[str], ignore: set[str]) -> tuple[int, int, int]:
    got = {p for p in got if p not in ignore and p != "/"}
    return len(got & want), len(got), len(want)


def score(name: str, schema: bool = True) -> dict[str, Any]:
    exp = json.loads((HERE / f"{name}.expected.json").read_text())
    site = run(name, schema)["site"]
    ignore = {p.lower() for p in exp.get("ignore", [])}
    services = {path(u) for c in site["services"]["clusters"] for u in c["pages"]}
    cities = {path(u) for u in site["cities"]["city_pages"]}
    # An FAQ section on another page is shown as such, not as an FAQ page: score it as none.
    trust_got = {
        t["key"]: (
            path(t["url"])
            if t["status"] == "found" and t["url"] and not t.get("section")
            else None
        )
        for t in site["trust"]
    }
    trust_ok = 0
    trust_wrong: list[str] = []
    for key, want in exp["trust"].items():
        accepted = want if isinstance(want, list) else [want]
        accepted = [a.lower().rstrip("/") if a else None for a in accepted]
        if trust_got.get(key) in accepted:
            trust_ok += 1
        else:
            trust_wrong.append(f"{key}: got {trust_got.get(key)}, want {want}")
    want_s = {p.lower() for p in exp["service_pages"]}
    want_c = {p.lower() for p in exp["city_pages"]}
    return {
        "services": _counts(services, want_s, ignore),
        "cities": _counts(cities, want_c, ignore),
        "trust": (trust_ok, len(exp["trust"])),
        "missed_services": sorted(want_s - services),
        "wrong_services": sorted(services - want_s - ignore - {"/"}),
        "missed_cities": sorted(want_c - cities),
        "wrong_cities": sorted(cities - want_c - ignore - {"/"}),
        "wrong_trust": trust_wrong,
    }


def totals(results: dict[str, dict[str, Any]]) -> dict[str, float]:
    def pr(kind: str) -> tuple[float, float]:
        tp = sum(r[kind][0] for r in results.values())
        got = sum(r[kind][1] for r in results.values())
        want = sum(r[kind][2] for r in results.values())
        return (tp / got if got else 1.0), (tp / want if want else 1.0)

    sp, sr = pr("services")
    cp, cr = pr("cities")
    ok = sum(r["trust"][0] for r in results.values())
    all_ = sum(r["trust"][1] for r in results.values())
    return {
        "services_precision": round(sp, 3),
        "services_recall": round(sr, 3),
        "cities_precision": round(cp, 3),
        "cities_recall": round(cr, 3),
        "trust_accuracy": round(ok / all_, 3),
    }


def table(results: dict[str, dict[str, Any]]) -> str:
    rows = ["site            services (right/found/expected)  cities  trust"]
    for name, r in results.items():
        s, c, t = r["services"], r["cities"], r["trust"]
        rows.append(
            f"{name:15} {s[0]:>3}/{s[1]:>3}/{s[2]:>3}                       "
            f"{c[0]}/{c[1]}/{c[2]}   {t[0]}/{t[1]}"
        )
    rows.append(json.dumps(totals(results)))
    return "\n".join(rows)


if __name__ == "__main__":
    if "--record-ai" in sys.argv:  # paid: one AI call per site
        import asyncio

        chosen = [a for a in sys.argv[1:] if not a.startswith("--")] or names()
        for n in chosen:
            print(f"{n}: {asyncio.run(record_ai(n))} pages labeled")
    detail = "--detail" in sys.argv
    results = {n: score(n) for n in names()}
    print(table(results))
    if detail:
        for n, r in results.items():
            for k in (
                "missed_services",
                "wrong_services",
                "missed_cities",
                "wrong_cities",
                "wrong_trust",
            ):
                if r[k]:
                    print(f"  {n} {k}: {r[k]}")
    if "--update" in sys.argv:
        BASELINE.write_text(json.dumps(totals(results), indent=2) + "\n")
        print(f"baseline saved to {BASELINE.name}")
