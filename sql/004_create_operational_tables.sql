CREATE TABLE IF NOT EXISTS aranet.sync_run (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    command text NOT NULL,
    endpoint text,
    scope_key text,
    status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at timestamptz,
    pages_read integer NOT NULL DEFAULT 0,
    rows_received bigint NOT NULL DEFAULT 0,
    rows_inserted bigint NOT NULL DEFAULT 0,
    rows_updated bigint NOT NULL DEFAULT 0,
    error_message text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS aranet.sync_state (
    endpoint text NOT NULL,
    scope_key text NOT NULL DEFAULT 'all',
    watermark timestamptz,
    next_token text,
    last_success_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (endpoint, scope_key)
);

CREATE TABLE IF NOT EXISTS aranet.sync_gap (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    endpoint text NOT NULL,
    scope_key text NOT NULL DEFAULT 'all',
    gap_from timestamptz NOT NULL,
    gap_to timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'resolved', 'failed')),
    attempts integer NOT NULL DEFAULT 0,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (gap_to > gap_from),
    UNIQUE (endpoint, scope_key, gap_from, gap_to)
);

CREATE TABLE IF NOT EXISTS aranet.resource_snapshot (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resource_type text NOT NULL,
    resource_id text NOT NULL,
    payload_hash text NOT NULL,
    payload jsonb NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (resource_type, resource_id, payload_hash)
);

