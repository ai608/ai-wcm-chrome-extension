-- The quick AI check (kind 'lite') is gone; only the full report runs. A quick check still marked
-- running would hold the one-running-run-per-audit index for ever, because nothing finishes it.
UPDATE extension.ai_visibility_runs
SET status = 'failed', error = 'interrupted', finished_at = now()
WHERE kind = 'lite' AND status = 'running';
