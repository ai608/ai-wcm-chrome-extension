"""Full AI visibility report: the checks before a run, starting it, and resuming it after a
restart. No HTTP here; the routes in app/api/v1/research.py call this."""

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.rate_limit import rate_limit
from app.models.user import UserProfile
from app.repositories.audit_repository import AuditRepository, to_wire
from app.services import ai_report, ai_visibility
from app.services.audit_runner import fetch_audit, track


async def guard(
    repo: AuditRepository, audit_id: str, profile: UserProfile, *, paid: bool = True
) -> dict[str, Any]:
    """Checks shared by the AI visibility endpoints. Returns the audit (wire shape).
    `paid=False` (writing the questions: one cheap call) skips the run rate limit and budget."""
    audit = to_wire(await fetch_audit(repo, audit_id))
    if not ai_visibility.enabled():
        raise AppError(
            503,
            "upstream_error",
            "AI visibility is not set up yet (AI_VISIBILITY_MODELS, OPENROUTER_API_KEY).",
        )
    if audit["status"] in ("queued", "running"):
        raise AppError(409, "audit_running", "Wait for the audit to finish first.")
    if not paid:
        return audit
    rate_limit(f"ai_vis:{profile.id}", 6, 3600)
    budget = round(settings.AI_VISIBILITY_DAILY_BUDGET_USD * 1_000_000)
    if await repo.ai_spend_micro(profile.id) >= budget:
        raise AppError(
            429, "budget_reached", "Daily AI visibility budget reached. Try tomorrow."
        )
    return audit


def spawn(
    repo: AuditRepository, http: httpx.AsyncClient, run_id: str, audit: dict[str, Any]
) -> None:
    track(asyncio.create_task(ai_report.run_job(repo, http, run_id, audit)))


async def suggest_questions(
    repo: AuditRepository,
    http: httpx.AsyncClient,
    audit_id: str,
    profile: UserProfile,
) -> dict[str, Any]:
    """Step 1 of the full report: write the questions and say how big the run would be.
    Nothing is saved and no run starts; the user reviews the questions, then approves them."""
    audit = await guard(repo, audit_id, profile, paid=False)
    rate_limit(f"ai_q:{profile.id}", 20, 3600)
    cfg = ai_report.plan(None, None)
    prompts, source = await ai_report.make_prompts(http, audit, cfg["n_prompts"], {})
    return {
        "prompts": prompts,
        "source": source,
        "engines": [e["label"] for e in cfg["engines"]],
        "runs": cfg["runs"],
        "max_questions": settings.AI_VISIBILITY_FULL_PROMPTS,
        "max_calls": settings.AI_VISIBILITY_FULL_MAX_CALLS,
    }


async def start_report(
    repo: AuditRepository,
    http: httpx.AsyncClient,
    audit_id: str,
    profile: UserProfile,
    prompts: list[str] | None,
    n_prompts: int | None,
    runs: int | None,
) -> dict[str, Any]:
    """Step 2: check the approved questions, start the report in the background, return the audit."""
    audit = await guard(repo, audit_id, profile)
    mine = list(
        dict.fromkeys(" ".join(p.split())[:200] for p in prompts or [] if p.strip())
    )
    if len(mine) > settings.AI_VISIBILITY_FULL_PROMPTS:
        raise AppError(
            422,
            "too_many_questions",
            f"At most {settings.AI_VISIBILITY_FULL_PROMPTS} questions. Remove "
            f"{len(mine) - settings.AI_VISIBILITY_FULL_PROMPTS}.",
        )
    # The user approves these exactly, so nothing is dropped silently. A question that names
    # the clinic would inflate the score, so it is refused instead.
    names = ai_visibility.build_target(audit).patterns
    if bad := next((p for p in mine if any(pat.search(p) for pat in names)), None):
        raise AppError(
            422,
            "question_names_clinic",
            f"Remove the clinic's name from this question, or the score is inflated: {bad}",
        )
    cfg = ai_report.plan(len(mine) or n_prompts, runs)
    if mine:
        cfg["prompts"] = mine
        cfg["prompts_source"] = "user"
        cfg["n_prompts"] = len(cfg["prompts"])
        cfg["calls"] = cfg["n_prompts"] * len(cfg["engines"]) * cfg["runs"]
    if cfg["calls"] > settings.AI_VISIBILITY_FULL_MAX_CALLS:
        raise AppError(
            422,
            "too_many_calls",
            f"This run would make {cfg['calls']} calls; the limit is "
            f"{settings.AI_VISIBILITY_FULL_MAX_CALLS}. Use fewer questions or repeats.",
        )
    run_id = await repo.create_ai_run(audit_id, profile.id, cfg)
    if run_id is None:
        raise AppError(
            409, "already_running", "An AI visibility check is already running."
        )
    spawn(repo, http, run_id, audit)
    return to_wire(await fetch_audit(repo, audit_id))


async def resume_full_runs(repo: AuditRepository, http: httpx.AsyncClient) -> int:
    """At start-up: continue full reports that a restart interrupted (answers already paid for
    are kept). A report that cannot be continued is failed, because a run left `running` would
    block the audit's next report for ever (one running report per audit)."""
    n = 0
    for run_id in await repo.running_full_runs():
        try:
            run = await repo.get_ai_run(run_id)
            audit = await repo.get(run["audit_id"]) if run else None
            if audit is None:
                await repo.save_ai_run(
                    run_id,
                    status="failed",
                    error="interrupted",
                    finished=True,
                )
                continue
            spawn(repo, http, run_id, to_wire(audit))
            n += 1
        except Exception:  # one bad run must not stop the others
            logging.getLogger(__name__).exception("could not resume run %s", run_id)
    return n


async def answers_page(
    repo: AuditRepository,
    run_id: str,
    *,
    engine: str | None,
    prompt: int | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Full answer texts of one report, a page at a time (they are too big for the audit)."""
    try:
        run = await repo.get_ai_run(run_id)
    except ValueError:  # not a UUID
        run = None
    if run is None or run["kind"] != "full":
        raise AppError(404, "run_not_found", "AI visibility report not found")
    rows = await repo.ai_answer_page(
        run_id, engine=engine, prompt_idx=prompt, limit=limit, offset=offset
    )
    return {
        "prompts": run["config"].get("prompts", []),
        "items": [
            {
                "prompt": r["prompt_idx"],
                "engine": r["engine"],
                "run": r["run_no"],
                "ok": r["status"] == "ok",
                "text": ai_visibility.stored_text(r["text"] or ""),
                "sources": r["urls"][:20],
                "error": r["error"],
                "facts": r["facts"],
            }
            for r in rows
        ],
    }
