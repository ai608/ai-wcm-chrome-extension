# AI Visibility: Implementation Plan

Status: draft for review. Date: 2026-11-04.
Source studied: `~/Downloads/AI-Visibility-Report-POC-main.zip` (the POC).
Target: this repo (`backend/` O4 API and `extension/`).

## 1. Terms used in this plan

| Term | Meaning |
|---|---|
| AI visibility | How often, and how well, a brand appears in answers from AI assistants (ChatGPT, Gemini, and others). |
| GEO / AEO | Generative Engine Optimization / Answer Engine Optimization. The work of making a brand appear in AI answers. |
| LLM | Large language model. The AI that writes the answers. |
| OpenRouter | One API that gives access to many LLMs. O4 already uses it. |
| Fan-out | Sending many requests at the same time. Here: prompts x engines x runs. |
| Judge | A second LLM call that reads an answer and returns structured facts (mentioned? rank? sentiment?). |
| Visibility Index (VI) | A 0-100 score the POC calculates from mentions, rank, citations and sentiment. |
| Share of Voice (SoV) | The share of all brand mentions that belong to one brand. |
| Wilson interval | A statistics method. It gives a range (for example 20%-55%) instead of one number, so small samples do not mislead. |
| Citation | A link in the answer that points to the brand's own website. |
| Trace | The step-by-step log O4 already stores for each audit (`audits.trace`). |
| Migration | A SQL file that changes the database. O4 runs them at start-up. |
| Feature flag | A setting that turns a feature on or off without a code change. |
| Idempotent | Doing the same request twice has the same result as doing it once. |
| SSRF | Server-side request forgery. An attacker makes your server fetch an internal address. |
| Prompt injection | Text inside data (such as a web page) that tries to give orders to the LLM. |

## 2. What the POC does

The POC is a separate app (FastAPI + React + Supabase/SQLite). It runs this pipeline:

1. Detect the category and the competitors of the brand (LLM).
2. Generate 25 / 50 / 100 search-style prompts (LLM).
3. Send each prompt to 5 engines, 1 or 3 times each (125 to 1500 calls).
4. Send every answer to the judge LLM (same number of calls again).
5. Calculate VI, SoV, a prompt-by-engine matrix and confidence ranges.
6. Stream progress to the UI and export a PDF.

The math is good and small (`metrics.py`, 260 lines). The rest does not fit O4.

## 3. What O4 already has (do not rebuild)

| Need | Already in this repo |
|---|---|
| Endpoint | `POST /research/audits/{id}/ai-visibility`. It is a stub that returns 503 (`api/v1/stubs.py`). |
| Setting | `AI_VISIBILITY_MODELS` in `core/config.py` (empty today). |
| Storage | `research` JSONB column on `extension.audits`. `empty_research()` already holds an `ai_visibility` slot. |
| UI | "AI Visibility" sub-tab (`ResearchSubTabs.tsx`), `AiVisibility` type, mock data and report section. |
| Wire contract | `{ prompts, engines: [{ engine, cited, citedBusinesses, answerExcerpt }] }`. |
| LLM client | `services/llm.py` (`chat_json`). Needs a plain-text variant with web search. |
| Real competitor list | `research.local_competitors` (Apify Google Maps data). Better than LLM-guessed competitors. |
| Safe URL handling | `site_audit.normalize_url` and the IP check. Blocks SSRF. |
| Progress | The `trace` log, and the extension already polls while any section is `running`. |
| Rate limit | `core/rate_limit.py` (per process). |
| Job runner | `_tasks` + `asyncio.create_task` in `research.py`, with the start-up sweeper `fail_interrupted`. |

Conclusion: the front door exists. We need to build the room behind it.

## 4. What we must NOT copy from the POC

| POC code | Problem | O4 action |
|---|---|---|
| Sync `supabase` client inside `async` functions | Blocks the event loop. | Use `asyncpg` through `AuditRepository`. |
| `PROGRESS` dict in memory | Lost on restart. Wrong with more than one instance. | Use `trace` in the database. |
| `run_queries` uses one `asyncio.gather` | Progress shows 0% then 100%. It is not real. | Use a bounded worker pool. Save each answer when it finishes. |
| `pandas`, `numpy`, `langchain_classic`, `bs4` | Heavy. `mypy --strict` fails on them. | Pure Python (about 100 lines) + `selectolax` + `pydantic`. |
| Search for `response_id` in a loop | O(n^2). Slow at 1500 calls. | Use a dict keyed by `(prompt, engine, run)`. |
| `httpx.get(user_url)` with no guard | SSRF risk. | Reuse `site_audit.normalize_url`. |
| LLM guesses the competitors | Can invent companies. | Use `local_competitors` first. LLM only as fallback. |
| Judge `sentiment` float turned into a word, then back into a number | Loses data. | Keep the float. |
| Temperature 0.7 and no stored model versions | Old and new reports cannot be compared. | Store model IDs, prompt version and scoring version per run. |
| No auth, no cost cap | Anyone can start 1500 paid calls. | Use `require_extension_access`, a cost cap and a rate limit. |

Security note: the older zip (`AI-Visibility-Report-POC.zip`) contains a real `backend/.env`. I did not open it. Rotate those keys if that zip was shared. Never commit a `.env`.

## 5. Recommended approach: two releases

### Release 1: "Lite" (fills the existing stub)

Goal: an SDR clicks "Check AI visibility" and gets an answer in 20-40 seconds. No contract change in the extension.

Backend:

1. New file `app/services/ai_visibility.py`.
2. Prompts: default to 3 local prompts built from the audit (top service + city). Example: "best med spa for Botox in Austin". Let the SDR edit them (UI already does).
3. For each prompt x engine, call OpenRouter with web search. Run them in parallel with a limit of 8.
4. Decide `cited` and `mentioned` with code, not with the judge:
   - `cited` = any URL in the answer (or in the OpenRouter `annotations`) has the clinic's domain. Verify the field name against a real response first.
   - `mentioned` = the clinic name or an alias appears in the text (normalize case, punctuation and "Med Spa" / "Medical Spa").
5. Use the judge only for what code cannot do: "which other businesses were named" (`citedBusinesses`). Validate its JSON with pydantic. Clamp every number.
6. Save the result in `research.ai_visibility` (same pattern as `local_competitors`). Set `state` = `ready` or `failed`.
7. Replace the stub route. Return 503 "not set up" when `AI_VISIBILITY_MODELS` or `OPENROUTER_API_KEY` is empty (this is the feature flag, same as Apify).
8. Add `rate_limit("ai_vis:{user}", 5, 3600)` and refuse a second run while one is `running` for the same audit.

Extension: almost nothing. Add `usage` text ("12 answers checked") and show the failed engines.

Tests (copy the style of `tests/test_research.py`): fake OpenRouter with `httpx.MockTransport`. Cases: all ok, one engine 429, judge returns bad JSON, no key set, double click.

### Release 2: "Full report" (the POC's real value)

Goal: a measured score with a range, for the client report. It takes minutes, so it is a background job.

Data (new migration `YYYYMMDDHHMMSS_ai_visibility.sql`):

- `extension.ai_visibility_runs`: `id, audit_id, status, tier, models, prompt_version, scoring_version, cost_usd, metrics JSONB, created_at, finished_at`.
- `extension.ai_visibility_answers`: `run_id, prompt_id, engine, run_no, text, tokens, cost_usd, error, signals JSONB`.
- Keep raw answers out of `audits` (they are large). Keep only a summary and `run_id` in `research.ai_visibility`.

Backend:

1. `POST .../ai-visibility` returns 202 at once with the run in state `running`. The job saves each answer when it arrives.
2. Resume: on start-up, a run in `running` continues from the saved answers. (Today the sweeper marks interrupted audits `failed`. Do not do this for runs.)
3. Port `prompt_generator.md`, `judge.md` and `metrics.py` (pure Python). Prove parity: run the POC and O4 on the same saved answers and compare VI to 2 decimals. Keep that as a test.
4. Mark a run `partial` if fewer than 70% of the calls succeeded. Never show a score from a handful of answers without the range.
5. Write trace events (`ai:prompts`, `ai:query`, `ai:judge`, `ai:score`) so `AuditProgress.tsx` can show progress for free.

Extension:

- Change the mutation from "wait for the result" to "start, then poll". The code that polls while a section is `running` already exists.
- Show: mention rate ("4 of 12 answers"), the range, SoV bars against local competitors, and a small prompt x engine grid. Keep the side panel simple. Put the full grid in the report page.
- Update `auditSchema` in `schemas.ts` and the mock fixtures.

## 6. What a senior developer would add (you did not ask for these)

1. **Cost cap and cost log.** The Standard tier is about 750 answer calls plus 750 judge calls. Store `cost_usd` per answer (OpenRouter returns it). Stop the run when it crosses a hard limit. Alert on spikes. Do not guess prices. Measure them in Release 1.
2. **Honest numbers.** LLM answers change from run to run. Show "4 of 12 answers mentioned you", not only "VI 37". The weights (60/25/15) are a choice, not a law. Write them down. A client will ask how you got the number.
3. **Do not merge it into the site score yet.** The 0-100 site score is repeatable. AI visibility is not. Keep it as its own section until you trust it.
4. **Versioning.** Store model IDs, the prompt version and the scoring version in every run. If you change a weight, old reports must still make sense.
5. **Partial failure rules.** Decide now: how many failed calls are acceptable, what the UI shows, and whether a retry costs the SDR a new run.
6. **Prompt injection.** Answers come from web search. They are untrusted text. Tell the judge that the text is data. Validate the JSON. Never let it decide a URL fetch.
7. **SSRF and secrets.** Reuse the existing URL guard. Keep keys in Railway variables only.
8. **Privacy.** You send clinic names (not patient data) to third-party LLMs. Confirm this with the owner. Check the provider terms. Use the API, never scrape a chat website.
9. **Idempotency.** One running run per audit. A double click must not start two paid runs.
10. **Cache.** Reuse a recent run for the same domain and prompts (for example 7 days) unless the SDR forces a new one. This saves money.
11. **Local accuracy.** Use the city. Use real competitors from Google Maps. Match name aliases. Without this, the score is wrong for clinics.
12. **Observability.** Log run id, cost, latency and success rate. Add a dashboard line or alert.
13. **Tests that matter.** Metrics parity with the POC, a fake provider, bad-judge-JSON cases, and a wire-contract test between Python output and the `zod` schema.
14. **Rollout.** Ship Release 1 behind the empty-key flag. Try it on 5 known clinics. Compare with a manual check in ChatGPT. Then enable it for all SDRs.
15. **Runbook.** One page: how to turn it off, how to read a failed run, who owns the OpenRouter budget.
16. **Multi-instance warning.** `rate_limit` and `_tasks` work in one process only (the code says so). If Railway scales to 2 instances, move the limit and the job queue to the database first.

## 7. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Cost grows without notice | Money | Hard cap, per-user limit, cache |
| Answers are noisy | Wrong advice to a client | Multiple runs, ranges, plain wording |
| Provider model is retired or renamed | Run fails | Models in settings, not code. Log the ID per run |
| Deploy kills a long run | Lost spend | Save each answer. Resume on start |
| Judge makes a mistake | Wrong signal | Code decides mention and citation. Spot-check a sample |

## 8. Decisions needed from you

1. Who reads this first: the SDR on a call (Lite) or the client in a report (Full)? Recommendation: Lite first.
2. Which engines? The UI text says ChatGPT, Gemini, Perplexity and Claude. The POC also uses Grok. Recommendation: the four in the UI.
3. What monthly OpenRouter budget do you accept?
4. Should the score appear in the PDF/email report to clients? If yes, Release 2 is required.

## 9. Order of work

1. Spike (half a day): one real OpenRouter web-search call. Check where the citations appear in the response. Record the cost.
2. Release 1 backend + tests.
3. Release 1 extension polish. Try with 5 clinics.
4. Decision gate: is the signal useful? Only then start Release 2.
5. Release 2: migration, job, metrics port, parity test, polling UI, report section.
