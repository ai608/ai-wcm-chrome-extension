-- Full AI visibility report: many prompts x engines x repeats, scored with a range.
-- A run keeps only the compact result in `data`; every answer is its own row so a restart can
-- continue where it stopped (no paid call is made twice) and the big text stays out of `audits`.
ALTER TABLE extension.ai_visibility_runs
    ADD COLUMN kind TEXT NOT NULL DEFAULT 'lite' CHECK (kind IN ('lite', 'full')),
    -- Frozen at start: prompts, engines (label + model), repeats, versions, caps.
    ADD COLUMN config JSONB;

-- 'partial' = finished, but too many calls failed (or the cost cap stopped it) to trust the score.
ALTER TABLE extension.ai_visibility_runs DROP CONSTRAINT ai_visibility_runs_status_check;
ALTER TABLE extension.ai_visibility_runs
    ADD CONSTRAINT ai_visibility_runs_status_check
    CHECK (status IN ('running', 'ready', 'partial', 'failed'));

CREATE TABLE extension.ai_visibility_answers (
    run_id UUID NOT NULL REFERENCES extension.ai_visibility_runs(id) ON DELETE CASCADE,
    prompt_idx SMALLINT NOT NULL,
    engine TEXT NOT NULL,
    run_no SMALLINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
    text TEXT,
    urls JSONB,
    error TEXT,
    tokens INTEGER NOT NULL DEFAULT 0,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_micro BIGINT NOT NULL DEFAULT 0,
    -- What was read from the answer: per brand mentioned/rank/position/cited (by code) and
    -- sentiment (by the judge). NULL = not read yet; the job fills it and can be restarted.
    facts JSONB,
    judge_tokens INTEGER NOT NULL DEFAULT 0,
    judge_cost_micro BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, prompt_idx, engine, run_no)
);
