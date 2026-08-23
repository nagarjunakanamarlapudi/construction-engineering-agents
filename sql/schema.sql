CREATE TABLE IF NOT EXISTS project_records (
    record_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    revision TEXT NOT NULL,
    effective_date DATE NOT NULL,
    data_origin TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_url TEXT,
    access_scopes JSONB NOT NULL,
    metadata JSONB NOT NULL,
    payload JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS project_records_project_type_idx
    ON project_records (project_id, record_type);
CREATE INDEX IF NOT EXISTS project_records_status_idx
    ON project_records (project_id, status);
CREATE INDEX IF NOT EXISTS project_records_metadata_gin_idx
    ON project_records USING GIN (metadata);
