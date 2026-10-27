CREATE TABLE model_registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    version TEXT NOT NULL,
    display_name TEXT NOT NULL,
    model_type TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(model_id, version)
);

CREATE TABLE experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    seed INTEGER,
    status TEXT NOT NULL DEFAULT 'created'
        CHECK (status IN ('created','running','completed','failed','cancelled','step_limit','wall_timeout')),
    engine_version TEXT NOT NULL,
    software_version TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    parent_experiment_id INTEGER REFERENCES experiments(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER,
    error TEXT
);

CREATE TABLE experiment_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    repeat_index INTEGER NOT NULL DEFAULT 0,
    seed INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','completed','failed','cancelled','step_limit','wall_timeout')),
    steps INTEGER,
    sim_time REAL,
    metrics_json TEXT,
    summary_json TEXT,
    events_json TEXT,
    error TEXT,
    result_sha256 TEXT,
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER
);

CREATE TABLE result_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES experiment_runs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    content_json TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_runs_experiment ON experiment_runs(experiment_id);
CREATE INDEX idx_experiments_model ON experiments(model_id, model_version);
CREATE INDEX idx_experiments_status ON experiments(status);
