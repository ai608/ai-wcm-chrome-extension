-- What each audit's AI calls cost (micro-USD, exact from OpenRouter) and how many tokens they used.
-- Saved on the audit row so the Settings total is one SUM, not a scan of every run log.
ALTER TABLE extension.audits
    ADD COLUMN ai_cost_micro BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN ai_tokens INTEGER NOT NULL DEFAULT 0;
