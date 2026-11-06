-- Public report links. The extension sends the rendered report page as one HTML document; the
-- link serves that snapshot until expires_at (7 days). Only a hash of the token is kept.
CREATE TABLE extension.report_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id UUID NOT NULL REFERENCES extension.audits (id) ON DELETE CASCADE,
    token_hash BYTEA NOT NULL UNIQUE,
    html TEXT NOT NULL,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX report_shares_audit ON extension.report_shares (audit_id);
