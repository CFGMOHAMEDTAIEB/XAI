"""Offline tests for automatic migration discovery, tracking, and safety."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "run_all_migrations.py"
SPEC = importlib.util.spec_from_file_location("run_all_migrations", SCRIPT)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def make_migration(directory: Path, name: str, sql: str = "SELECT 1") -> None:
    (directory / name).write_text(sql, encoding="utf-8")


def test_fresh_database_plans_every_migration(tmp_path, monkeypatch):
    make_migration(tmp_path, "001_first.sql")
    make_migration(tmp_path, "002_second.sql")
    migrations = runner.discover_migrations(tmp_path)
    monkeypatch.setattr(runner, "_applied", lambda cursor, exists: {})
    monkeypatch.setattr(runner, "_legacy_present", lambda cursor, migration: False)

    baseline, pending = runner.migration_plan(object(), migrations, False)
    assert baseline == []
    assert [migration.version for migration in pending] == ["001", "002"]


def test_partially_and_fully_migrated_database(tmp_path, monkeypatch):
    make_migration(tmp_path, "001_first.sql")
    make_migration(tmp_path, "002_second.sql")
    migrations = runner.discover_migrations(tmp_path)
    first = migrations[0]
    monkeypatch.setattr(runner, "_legacy_present", lambda cursor, migration: False)
    monkeypatch.setattr(runner, "_applied", lambda cursor, exists: {"001": (first.filename, first.checksum)})
    assert [item.version for item in runner.migration_plan(object(), migrations, True)[1]] == ["002"]

    monkeypatch.setattr(
        runner,
        "_applied",
        lambda cursor, exists: {item.version: (item.filename, item.checksum) for item in migrations},
    )
    assert runner.migration_plan(object(), migrations, True) == ([], [])


def test_checksum_mismatch_stops_plan(tmp_path, monkeypatch):
    make_migration(tmp_path, "001_first.sql")
    migration = runner.discover_migrations(tmp_path)[0]
    monkeypatch.setattr(runner, "_applied", lambda cursor, exists: {"001": (migration.filename, "0" * 64)})
    with pytest.raises(runner.MigrationError, match="CHECKSUM_MISMATCH"):
        runner.migration_plan(object(), [migration], True)


def test_future_migrations_are_discovered_in_numeric_order(tmp_path):
    make_migration(tmp_path, "010_future.sql")
    make_migration(tmp_path, "002_second.sql")
    make_migration(tmp_path, "005_feature.sql")
    assert [item.version for item in runner.discover_migrations(tmp_path)] == ["002", "005", "010"]


class TransactionConnection:
    class Cursor:
        def __init__(self, owner):
            self.owner = owner

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql, parameters=None):
            self.owner.executions.append((sql, parameters))
            if self.owner.fail_sql and parameters is None:
                raise RuntimeError("private database failure")

    def __init__(self, fail_sql=False):
        self.fail_sql = fail_sql
        self.executions = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_migration_failure_rolls_back_without_recording_commit(tmp_path):
    make_migration(tmp_path, "005_failure.sql", "BROKEN MIGRATION")
    migration = runner.discover_migrations(tmp_path)[0]
    connection = TransactionConnection(fail_sql=True)
    with pytest.raises(RuntimeError):
        runner.apply_one(connection, migration, execute_sql=True)
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_successful_apply_records_checksum_in_same_transaction(tmp_path):
    make_migration(tmp_path, "005_success.sql", "SELECT 5")
    migration = runner.discover_migrations(tmp_path)[0]
    connection = TransactionConnection()
    runner.apply_one(connection, migration, execute_sql=True)
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.executions[0] == ("SELECT 5", None)
    assert connection.executions[1][1] == (migration.version, migration.filename, migration.checksum)


def test_idempotent_rerun_has_no_pending_work(tmp_path, monkeypatch):
    make_migration(tmp_path, "001_first.sql")
    migration = runner.discover_migrations(tmp_path)[0]
    monkeypatch.setattr(runner, "_applied", lambda cursor, exists: {"001": (migration.filename, migration.checksum)})
    monkeypatch.setattr(runner, "_legacy_present", lambda cursor, migration: pytest.fail("applied migration was probed"))
    assert runner.migration_plan(object(), [migration], True) == ([], [])


def test_concurrent_startup_uses_session_advisory_lock_and_unlock(tmp_path, monkeypatch):
    class Cursor:
        def __init__(self, owner):
            self.owner = owner

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql, parameters=None):
            self.owner.calls.append((sql, parameters))

    class Connection:
        def __init__(self):
            self.calls = []

        def cursor(self):
            return Cursor(self)

        def rollback(self):
            pass

        def commit(self):
            pass

        def close(self):
            pass

    env_file = tmp_path / "offline.env"
    env_file.write_text("DATABASE_URL=postgresql://u:p@h/db\n", encoding="utf-8")
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    make_migration(migration_dir, "001_first.sql")
    connection = Connection()
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda *args, **kwargs: connection))
    monkeypatch.setattr(runner, "MIGRATIONS_DIR", migration_dir)
    monkeypatch.setattr(runner, "_tracking_exists", lambda cursor: True)
    monkeypatch.setattr(runner, "migration_plan", lambda cursor, migrations, exists: ([], []))

    assert runner.run(["--env-file", str(env_file), "--apply"]) == 0
    lock_calls = [call for call in connection.calls if "pg_advisory_lock" in call[0]]
    unlock_calls = [call for call in connection.calls if "pg_advisory_unlock" in call[0]]
    assert lock_calls == [("SELECT pg_advisory_lock(%s)", (runner.LOCK_KEY,))]
    assert unlock_calls == [("SELECT pg_advisory_unlock(%s)", (runner.LOCK_KEY,))]


def test_legacy_applied_migration_is_baselined_not_executed(tmp_path, monkeypatch):
    make_migration(tmp_path, "003_legacy.sql", "MUST NOT EXECUTE")
    migration = runner.discover_migrations(tmp_path)[0]
    monkeypatch.setattr(runner, "_applied", lambda cursor, exists: {})
    monkeypatch.setattr(runner, "_legacy_present", lambda cursor, item: True)
    baseline, pending = runner.migration_plan(object(), [migration], False)
    assert baseline == [migration]
    assert pending == []


def test_docker_startup_is_fail_closed_and_copies_runner():
    dockerfile = (ROOT / "services" / "api_fastapi" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY scripts/run_all_migrations.py scripts/run_all_migrations.py" in dockerfile
    assert "python scripts/run_all_migrations.py --apply && exec uvicorn" in dockerfile
