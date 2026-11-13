-- Refresh-token rotation used to leave no way back: the server replaced the refresh token the
-- moment it answered, so an answer lost on the way (flaky network, a restart) logged the user
-- out. The token just replaced now works for a short time more, so the client can ask again.
ALTER TABLE extension.auth_sessions
    ADD COLUMN IF NOT EXISTS prev_refresh_hash TEXT,
    ADD COLUMN IF NOT EXISTS prev_refresh_until TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS auth_sessions_prev_refresh
    ON extension.auth_sessions (prev_refresh_hash) WHERE prev_refresh_hash IS NOT NULL;
