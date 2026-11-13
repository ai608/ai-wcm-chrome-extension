-- Saving a call outcome checks for the same save made a moment ago (a retry after a lost
-- answer must not add a second CRM note). That lookup is by contact, user and outcome.
CREATE INDEX IF NOT EXISTS call_outcomes_recent
    ON extension.call_outcomes (ghl_contact_id, user_id, outcome_id, created_at DESC);
