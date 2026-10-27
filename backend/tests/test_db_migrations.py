import sqlite3

from app.db.connection import connect
from app.db.migrations import apply_migrations, current_version


def test_fresh_db_migrates(tmp_path):
    db = str(tmp_path / "t.db")
    applied = apply_migrations(db)
    assert applied == [1, 2]
    conn = connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "schema_migrations",
        "experiments",
        "experiment_runs",
        "model_registrations",
        "result_artifacts",
        "batch_runs",
        "batch_items",
    } <= tables
    assert current_version(conn) == 2
    conn.close()


def test_migrations_idempotent(tmp_path):
    db = str(tmp_path / "t.db")
    apply_migrations(db)
    applied = apply_migrations(db)
    assert applied == []
    conn = connect(db)
    assert current_version(conn) == 2
    conn.close()


def test_status_check_constraints(tmp_path):
    db = str(tmp_path / "t.db")
    apply_migrations(db)
    conn = connect(db)
    conn.execute(
        "INSERT INTO experiments(name, model_id, model_version, spec_json, engine_version, software_version)"
        " VALUES ('x','queueing','1.0.0','{}','1','py')"
    )
    try:
        conn.execute("INSERT INTO experiment_runs(experiment_id, seed, status) VALUES (1, 1, 'bogus')")
        assert False, "should have failed"
    except sqlite3.IntegrityError:
        pass
    conn.rollback()
    conn.close()
