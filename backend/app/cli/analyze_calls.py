"""Analyze past GHL call transcripts and draft the next script version.

    uv run python -m app.cli.analyze_calls --max-calls 60

Writes scripts/v{N+1}.draft.json and scripts/v{N+1}.report.md for human review.
Nothing is published: the server only loads scripts/v*.json, never *.draft.json.
"""

import argparse
import asyncio
import copy
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.services import ghl, llm

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
MIN_SECONDS = 60
TRANSCRIPT_VERSION = "2021-04-15"
MAX_TRANSCRIPT_CHARS = 12_000
MIN_TRANSCRIPT_CHARS = 400
NO_TRANSCRIPT = (
    "No transcript found"  # GHL placeholder for calls it could not transcribe
)

EXTRACT_SYSTEM = """You analyze one outbound sales call transcript for a wellness-clinic \
marketing agency. Speaker labels are audio channels, not roles: work out who is the sales rep \
(the caller). Return JSON only:
{"conversation_type":"prospect|gatekeeper|voicemail_or_screening",
 "objections":[{"type":"short label","prospect_said":"...","rep_reply":"...","landed":true|false}],
 "answers":{"short topic":"what the prospect revealed"},
 "good_phrases":["rep wording that kept the prospect engaged"],
 "drop_off":"where/why the prospect disengaged, or empty",
 "reached_decision_maker":true|false}
Quote briefly. Never invent facts that are not in the transcript."""

SYNTH_SYSTEM = """You improve a cold-call script for a wellness-clinic marketing agency using \
aggregated call analysis. Return JSON only:
{"new_responses":[{"section_id":"opener|qualification","label":"<=40 chars","text":"<=300 chars, \
plain text, may use {{contact.first_name}} {{contact.company_name}} {{contact.city}}"}],
 "faq_items":[{"q":"...","a":"..."}],
 "flows":{"<existing response block id>":{"ask":"next question the rep asks (optional)",\
"options":[{"id":"unique-id","label":"what the prospect answers","say":"what the rep replies",\
"next":{"ask":"...","options":[...]}}]}},
 "report":"markdown: top objections with counts, what worked, where calls die, what changed and why"}
Rules: never mention prices, guarantees, or patient/medical outcomes. Only reference response ids \
that exist in the current script. Base every change on the evidence given."""


def latest_script_path() -> Path:
    files = [p for p in SCRIPTS.iterdir() if re.fullmatch(r"v\d+\.json", p.name)]
    return max(files, key=lambda p: int(p.stem[1:]))


def _text(seg: Any) -> str:
    if isinstance(seg, str):
        return "" if seg.strip() == NO_TRANSCRIPT else seg
    if isinstance(seg, dict):
        for k in ("transcript", "text", "sentence"):
            if isinstance(seg.get(k), str):
                return _text(seg[k])
    return ""


def transcript_text(data: Any) -> str:
    """GHL returns segments (shape not fully documented): join whatever text is there."""
    rows = data if isinstance(data, list) else None
    if rows is None and isinstance(data, dict):
        for k in ("transcriptions", "transcripts", "data", "segments"):
            if isinstance(data.get(k), list):
                rows = data[k]
                break
        else:
            return _text(data)
    lines = []
    for seg in rows or []:
        t = _text(seg).strip()
        if not t:
            continue
        who = seg.get("mediaChannel") if isinstance(seg, dict) else None
        lines.append(f"[{who}] {t}" if who is not None else t)
    return "\n".join(lines)


async def list_calls(http: httpx.AsyncClient, max_calls: int) -> list[dict[str, Any]]:
    loc = settings.GHL_SALES_LOCATION_ID
    calls: list[dict[str, Any]] = []
    after: str | None = None
    while len(calls) < max_calls:
        params: dict[str, Any] = {
            "locationId": loc,
            "lastMessageType": "TYPE_CALL",
            "limit": 50,
        }
        if after:
            params["startAfterDate"] = after
        page = (await ghl.get_json(http, "/conversations/search", params)).get(
            "conversations", []
        )
        if not page:
            break
        for conv in page:
            msgs = await ghl.get_json(
                http,
                f"/conversations/{conv['id']}/messages",
                {"type": "TYPE_CALL", "limit": 50},
            )
            for m in msgs.get("messages", {}).get("messages", []):
                dur = (m.get("meta") or {}).get("call", {}).get("duration", 0) or 0
                if (
                    m.get("messageType") == "TYPE_CALL"
                    and m.get("direction") == "outbound"
                    and dur >= MIN_SECONDS
                ):
                    calls.append(
                        {
                            "id": m["id"],
                            "contact_id": conv.get("contactId") or m.get("contactId"),
                            "seconds": dur,
                        }
                    )
        after = str(page[-1].get("lastMessageDate", ""))
        if not after:
            break
    return calls[:max_calls]


async def fetch_call(
    http: httpx.AsyncClient, call: dict[str, Any]
) -> dict[str, Any] | None:
    loc = settings.GHL_SALES_LOCATION_ID
    try:
        data = await ghl.get_json(
            http,
            f"/conversations/locations/{loc}/messages/{call['id']}/transcription",
            version=TRANSCRIPT_VERSION,
        )
        text = transcript_text(data)
        contact = await ghl.get_contact(http, call["contact_id"])
    except AppError:  # one bad call must not stop the run
        return None
    outcome = next(
        (
            t.split(":", 1)[1]
            for t in contact.get("tags", [])
            if t.startswith("call-outcome:")
        ),
        "unknown",
    )
    if len(text.strip()) < MIN_TRANSCRIPT_CHARS:
        return None
    return {**call, "text": text[:MAX_TRANSCRIPT_CHARS], "outcome": outcome}


def compact_script(script: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "section": s["id"],
            "responses": [
                {"id": b["id"], "label": b["label"], "text": b["text"]}
                for b in s["blocks"]
                if b["type"] == "response"
            ],
        }
        for s in script["sections"]
    ]


def aggregate(extractions: list[dict[str, Any]]) -> dict[str, Any]:
    objections: Counter[str] = Counter()
    landed: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    phrases: Counter[str] = Counter()
    drops: Counter[str] = Counter()
    by_outcome: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    for e in extractions:
        x = e["analysis"]
        by_type[str(x.get("conversation_type", "prospect"))] += 1
        if x.get("conversation_type") == "voicemail_or_screening":
            continue  # no sales conversation to learn from
        by_outcome[e["outcome"]] += 1
        for o in x.get("objections", []):
            t = str(o.get("type", "other")).lower()
            objections[t] += 1
            landed[t] += bool(o.get("landed"))
            examples.setdefault(t, [])
            if len(examples[t]) < 3:
                examples[t].append(
                    f"{o.get('prospect_said', '')} -> {o.get('rep_reply', '')}"
                )
        phrases.update(str(p) for p in x.get("good_phrases", []))
        if x.get("drop_off"):
            drops[str(x["drop_off"])[:120]] += 1
    return {
        "calls": len(extractions),
        "conversation_types": dict(by_type),
        "outcomes": dict(by_outcome),
        "objections": [
            {"type": t, "count": n, "reply_landed": landed[t], "examples": examples[t]}
            for t, n in objections.most_common(12)
        ],
        "good_phrases": [p for p, _ in phrases.most_common(15)],
        "drop_offs": [d for d, _ in drops.most_common(8)],
    }


_BAD = re.compile(
    r"\$\s?\d|guarantee|\d+\s?%|cure|heal(?:s|ed)?\b|patient outcome", re.IGNORECASE
)


def _clean_node(node: Any, depth: int, notes: list[str]) -> dict[str, Any] | None:
    """Keep a flow node only if well-formed and free of banned content (max 4 levels)."""
    if (
        not isinstance(node, dict)
        or depth > 3
        or not isinstance(node.get("options"), list)
    ):
        return None
    options = []
    for o in node["options"]:
        if not isinstance(o, dict):
            continue
        label, say = str(o.get("label", "")).strip(), str(o.get("say", "")).strip()
        if not (label and say and o.get("id")) or _BAD.search(label + " " + say):
            notes.append(f"skipped flow option {label!r}")
            continue
        clean: dict[str, Any] = {
            "id": str(o["id"]),
            "label": label[:60],
            "say": say[:300],
        }
        if (nxt := _clean_node(o.get("next"), depth + 1, notes)) is not None:
            clean["next"] = nxt
        options.append(clean)
    if not options:
        return None
    out: dict[str, Any] = {"options": options}
    ask = str(node.get("ask", "")).strip()
    if ask and not _BAD.search(ask):
        out["ask"] = ask[:200]
    return out


def build_draft(
    current: dict[str, Any], synth: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Apply only safe, structured changes to a copy of the script. Returns (draft, notes)."""
    draft = copy.deepcopy(current)
    draft["version"] = current["version"] + 1
    notes: list[str] = []
    sections = {s["id"]: s for s in draft["sections"]}
    ids = {b["id"] for s in draft["sections"] for b in s["blocks"]}
    n = 0
    for r in synth.get("new_responses", []):
        sec, label, text = (
            sections.get(r.get("section_id")),
            str(r.get("label", "")),
            str(r.get("text", "")),
        )
        if not sec or not label or not text or _BAD.search(text):
            notes.append(f"skipped response {label!r}")
            continue
        n += 1
        last = max(
            (i for i, b in enumerate(sec["blocks"]) if b["type"] == "response"),
            default=-1,
        )
        sec["blocks"].insert(
            last + 1,
            {
                "type": "response",
                "id": f"r-new-{draft['version']}-{n}",
                "label": label[:40],
                "text": text[:300],
            },
        )
    faq = next(
        (b for s in draft["sections"] for b in s["blocks"] if b["type"] == "faq"), None
    )
    for item in synth.get("faq_items", []):
        q, a = str(item.get("q", "")), str(item.get("a", ""))
        if faq and q and a and not _BAD.search(a):
            faq["items"].append({"q": q, "a": a})
        else:
            notes.append(f"skipped faq {q!r}")
    draft.pop("followups", None)
    ids = {
        b["id"] for s in draft["sections"] for b in s["blocks"]
    }  # incl. new responses
    draft["flows"] = {
        k: node
        for k, v in synth.get("flows", {}).items()
        if k in ids and (node := _clean_node(v, 0, notes)) is not None
    }
    return draft, notes


async def run(max_calls: int) -> None:
    current = json.loads(latest_script_path().read_text())
    async with httpx.AsyncClient(timeout=30) as http:
        calls = await list_calls(http, max_calls)
        print(f"{len(calls)} calls >= {MIN_SECONDS}s found")
        fetched = [
            c for c in await asyncio.gather(*(fetch_call(http, c) for c in calls)) if c
        ]
        print(f"{len(fetched)} with transcripts")
        if len(fetched) < 5:
            raise SystemExit(
                "Too few transcripts to find patterns (need ~30+). Is transcription enabled?"
            )
        sem = asyncio.Semaphore(4)

        async def extract(c: dict[str, Any]) -> dict[str, Any] | None:
            async with sem:
                try:
                    return {
                        "outcome": c["outcome"],
                        "analysis": await llm.chat_json(
                            http, EXTRACT_SYSTEM, c["text"], max_tokens=1200
                        ),
                    }
                except AppError:
                    return None

        extractions = [
            e for e in await asyncio.gather(*(extract(c) for c in fetched)) if e
        ]
        agg = aggregate(extractions)
        synth = await llm.chat_json(
            http,
            SYNTH_SYSTEM,
            json.dumps({"current_script": compact_script(current), "analysis": agg}),
            max_tokens=4000,
        )
    draft, notes = build_draft(current, synth)
    v = draft["version"]
    (SCRIPTS / f"v{v}.draft.json").write_text(json.dumps(draft, indent=2))
    report = (
        str(synth.get("report", "")) + "\n\n## Evidence\n" + json.dumps(agg, indent=2)
    )
    if notes:
        report += "\n\n## Rejected by guard\n" + "\n".join(f"- {x}" for x in notes)
    (SCRIPTS / f"v{v}.report.md").write_text(report)
    print(
        f"Wrote scripts/v{v}.draft.json and scripts/v{v}.report.md. Review, then rename to v{v}.json."
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=60)
    asyncio.run(run(ap.parse_args().max_calls))
