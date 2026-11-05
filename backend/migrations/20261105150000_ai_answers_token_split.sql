-- The answers table first shipped without the input/output token split. Databases that already
-- ran 20261105120000 need these columns; newer ones have them from that migration, hence IF NOT EXISTS.
ALTER TABLE extension.ai_visibility_answers
    ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS completion_tokens INTEGER NOT NULL DEFAULT 0;
