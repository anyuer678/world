-- Phase 4: batch experiments (parameter grid search + repeated trials).
CREATE TABLE batch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    grid_json TEXT NOT NULL,
    repeats INTEGER NOT NULL,
    seed_strategy TEXT NOT NULL,
    seed_base INTEGER,
    max_retries INTEGER NOT NULL,
    concurrency INTEGER NOT NULL,
    per_run_wall_seconds REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    total_items INTEGER NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER
);
CREATE INDEX idx_batch_runs_model ON batch_runs(model_id);

CREATE TABLE batch_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batch_runs(id) ON DELETE CASCADE,
    item_index INTEGER NOT NULL,
    combo_json TEXT NOT NULL,
    repeat_index INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    steps INTEGER,
    sim_time REAL,
    metrics_json TEXT,
    result_sha256 TEXT,
    error TEXT,
    duration_ms INTEGER,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX idx_batch_items_batch ON batch_items(batch_id, item_index);
