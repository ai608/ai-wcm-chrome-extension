CREATE SCHEMA IF NOT EXISTS extension;

CREATE TABLE IF NOT EXISTS extension.schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE extension.personalized_scripts (
    ghl_contact_id TEXT PRIMARY KEY,
    script_version INT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('generating', 'ready', 'failed')),
    slots JSONB NOT NULL DEFAULT '{}',
    error TEXT,
    input_hash TEXT,
    model TEXT,
    generated_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE extension.jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL CHECK (kind IN ('script', 'audit', 'on_demand')),
    subject TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    requested_by UUID,
    error TEXT,
    tokens_in INT,
    tokens_out INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX jobs_active_uq ON extension.jobs (kind, subject, (detail->>'key'))
    WHERE status IN ('queued', 'running');

CREATE TABLE extension.call_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ghl_contact_id TEXT NOT NULL,
    user_id UUID NOT NULL,
    outcome_id TEXT NOT NULL,
    booked BOOLEAN NOT NULL,
    note TEXT NOT NULL,
    ghl_note_id TEXT,
    tag TEXT NOT NULL,
    script_version INT NOT NULL,
    missing_fields TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE extension.history_briefs (
    ghl_contact_id TEXT PRIMARY KEY,
    activity_hash TEXT NOT NULL,
    text TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE extension.audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain TEXT NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'ready', 'partial', 'failed')),
    error TEXT,
    section_state JSONB NOT NULL DEFAULT '{}',
    overview JSONB,
    business JSONB,
    on_page JSONB,
    schema_data JSONB,
    site JSONB,
    convert JSONB,
    research JSONB NOT NULL DEFAULT '{}',
    hints JSONB NOT NULL DEFAULT '{}',
    report_intro TEXT,
    requested_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX audits_domain_created ON extension.audits (domain, created_at DESC);

CREATE TABLE extension.contact_research (
    ghl_contact_id TEXT PRIMARY KEY,
    audit_id UUID NOT NULL REFERENCES extension.audits(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE extension.report_sends (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id UUID NOT NULL REFERENCES extension.audits(id),
    user_id UUID NOT NULL,
    recipient_email TEXT NOT NULL,
    email_sent BOOLEAN NOT NULL,
    slack_sent BOOLEAN NOT NULL,
    ghl_contact_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE extension.audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID,
    action TEXT NOT NULL,
    ghl_contact_id TEXT,
    detail JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
