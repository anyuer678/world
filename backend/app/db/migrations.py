"""Sequential SQL migration runner. Files: backend/migrations/NNNN_name.sql.
Each file is applied at most once inside a transaction and recorded in
schema_migrations. Re-running is a no-op (idempotent)."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .connection import connect

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _migration_files() -> list[tuple[int, str, Path]]:
    out = []
    for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = re.match(r"^(\d+)_", p.name)
        if not m:
            raise RuntimeError(f"migration file must be named NNNN_name.sql: {p.name}")
        out.append((int(m.group(1)), p.name, p))
    out.sort(key=lambda t: t[0])
    versions = [v for v, _, _ in out]
    if len(set(versions)) != len(versions):
        raise RuntimeError("duplicate migration version numbers")
    return out


def apply_migrations(db_path: str, conn: sqlite3.Connection | None = None) -> list[int]:
    """Apply pending migrations; returns versions applied this call."""
    own = conn is None
    if own:
        conn = connect(db_path)
    applied: list[int] = []
    try:
        conn.executescript(_SCHEMA)
        done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version, name, path in _migration_files():
            if version in done:
                continue
            sql = path.read_text(encoding="utf-8")
            script = f"BEGIN;\n{sql}\nINSERT INTO schema_migrations(version, name) VALUES ({version}, '{name}');\nCOMMIT;"
            try:
                conn.executescript(script)
            except sqlite3.Error:
                conn.execute("ROLLBACK")
                raise
            applied.append(version)
    finally:
        if own:
            conn.close()
    return applied


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0]) if row and row[0] is not None else 0
