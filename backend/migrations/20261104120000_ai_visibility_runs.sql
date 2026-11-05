-- One row per AI visibility run. `data` holds the compact result and the folded run log
-- (excerpts only, never full answers). Cost is stored as integer micro-USD so sums are exact.
CREATE TABLE extension.ai_visibility_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id UUID NOT NULL REFERENCES extension.audits(id) ON DELETE CASCADE,
    requested_by UUID NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'ready', 'failed')),
    error TEXT,
    data JSONB,
    cost_micro BIGINT NOT NULL DEFAULT 0,
    tokens INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
-- Latest run of an audit (read on every audit fetch).
CREATE INDEX ai_visibility_runs_audit ON extension.ai_visibility_runs (audit_id, created_at DESC);
-- Daily budget check per user.
CREATE INDEX ai_visibility_runs_user ON extension.ai_visibility_runs (requested_by, created_at DESC);
-- The database, not the app, guarantees one running run per audit (double click, two instances).
CREATE UNIQUE INDEX ai_visibility_one_running ON extension.ai_visibility_runs (audit_id)
    WHERE status = 'running';
