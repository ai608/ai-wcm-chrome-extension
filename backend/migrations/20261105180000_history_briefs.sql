-- AI brief at the top of the History tab. extension.history_briefs was created by init.sql as one
-- row per contact and nothing has used it; this reshapes it, keeping any rows, into an append-only
-- table: a new brief is a new row, never an update, so the AI spend summary keeps every cost.
-- `input_hash` is the hash of the facts sent to the model; the same facts under the same prompt
-- never call the model twice (and two panels racing end with one row). Only the brief text and
-- a hash are kept, never the notes or messages.
ALTER TABLE extension.history_briefs DROP CONSTRAINT history_briefs_pkey;
ALTER TABLE extension.history_briefs RENAME COLUMN activity_hash TO input_hash;
ALTER TABLE extension.history_briefs RENAME COLUMN generated_at TO created_at;
ALTER TABLE extension.history_briefs
    ADD COLUMN id UUID NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN prompt_version SMALLINT NOT NULL DEFAULT 1,
    ADD COLUMN model TEXT NOT NULL DEFAULT '',
    -- old rows have no author; the all-zero UUID marks them
    ADD COLUMN requested_by UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    ADD COLUMN cost_micro BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE extension.history_briefs
    ADD PRIMARY KEY (id),
    ADD CONSTRAINT history_briefs_facts_key UNIQUE (ghl_contact_id, input_hash, prompt_version);
ALTER TABLE extension.history_briefs
    ALTER COLUMN prompt_version DROP DEFAULT,
    ALTER COLUMN model DROP DEFAULT,
    ALTER COLUMN requested_by DROP DEFAULT;
-- Newest brief of a contact (the fallback when a fresh one cannot be made).
CREATE INDEX history_briefs_contact ON extension.history_briefs (ghl_contact_id, created_at DESC);
-- Spend summary windows.
CREATE INDEX history_briefs_created ON extension.history_briefs (created_at) WHERE cost_micro > 0;
