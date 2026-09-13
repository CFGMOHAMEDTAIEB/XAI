"""Offline tests for migration 004 and its safe runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "run_migration_004.py"
MIGRATION = ROOT / "services" / "api_fastapi" / "migrations" / "004_schema_alignment.sql"
SPEC = importlib.util.spec_from_file_location("run_migration_004", SCRIPT)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class MetadataConnection:
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    def cursor(self):
        return self.Cursor()


def install_metadata(monkeypatch, *, columns=None, refresh_exists=False, indexes=None, constraints=None):
    monkeypatch.setattr(runner, "_columns", lambda cursor, table: (columns or {}).get(table, {}))
    monkeypatch.setattr(runner, "_table_exists", lambda cursor, table: refresh_exists)
    monkeypatch.setattr(runner, "_indexes", lambda cursor: indexes or {})
    monkeypatch.setattr(runner, "_constraints", lambda cursor: constraints or {})


def full_columns():
    return {table: dict(specs) for table, specs in runner.COLUMN_SPECS.items()}


def full_indexes():
    return {
        "ix_refresh_tokens_user_id": "CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id)",
        "ix_refresh_tokens_token_hash": "CREATE UNIQUE INDEX ix_refresh_tokens_token_hash ON refresh_tokens (token_hash)",
    }


def full_constraints():
    return {
        "refresh_tokens_pkey": ("p", "PRIMARY KEY (id)"),
        "refresh_tokens_user_id_fkey": ("f", "FOREIGN KEY (user_id) REFERENCES users(id)"),
    }


def test_unapplied_partial_and_applied_states(monkeypatch):
    install_metadata(monkeypatch)
    assert runner.inspect_schema(MetadataConnection()).state == "NOT_APPLIED"

    install_metadata(monkeypatch, columns={"audit_events": runner.COLUMN_SPECS["audit_events"]})
    partial = runner.inspect_schema(MetadataConnection())
    assert partial.state == "PARTIAL"
    assert "audit_events.updated_at" not in partial.missing

    install_metadata(
        monkeypatch,
        columns=full_columns(),
        refresh_exists=True,
        indexes=full_indexes(),
        constraints=full_constraints(),
    )
    assert runner.inspect_schema(MetadataConnection()) == runner.Inspection("APPLIED", ())


def test_metadata_failure_is_an_exception_not_missing_object(monkeypatch):
    def fail(cursor, table):
        raise RuntimeError("connection details must not be emitted")

    monkeypatch.setattr(runner, "_table_exists", fail)
    with pytest.raises(RuntimeError):
        runner.inspect_schema(MetadataConnection())


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("postgresql+psycopg://u:p@h/d", "postgresql://u:p@h/d"),
        ("postgresql://u:p@h/d", "postgresql://u:p@h/d"),
        ("postgres://u:p@h/d", "postgres://u:p@h/d"),
    ],
)
def test_database_schemes(source, expected):
    assert runner.normalize_database_url(source) == expected


def test_check_only_reports_safe_missing_names_without_connecting(tmp_path, capsys, monkeypatch):
    class Connection:
        def rollback(self):
            pass

        def close(self):
            pass

    env_file = tmp_path / "offline.env"
    env_file.write_text("DATABASE_URL=postgresql://private:secret@host/db\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda *args, **kwargs: Connection()))
    monkeypatch.setattr(runner, "inspect_schema", lambda connection: runner.Inspection("PARTIAL", ("audit_events.updated_at",)))

    assert runner.run(["--env-file", str(env_file), "--check-only"]) == 1
    output = capsys.readouterr().out
    assert output == (
        "DATABASE_CONNECTION = PASS\n"
        "MIGRATION_004_STATE = PARTIAL\n"
        "MISSING_OBJECT = audit_events.updated_at\n"
    )
    assert "private" not in output and "secret" not in output


def test_apply_is_transactional_and_post_verified_offline(tmp_path, capsys, monkeypatch):
    class Cursor:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql):
            self.connection.executed.append(sql)

    class Connection:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0
            self.executed = []

        def cursor(self):
            return Cursor(self)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            pass

    connection = Connection()
    states = iter((runner.Inspection("PARTIAL", ("audit_events.updated_at",)), runner.Inspection("APPLIED", ()), runner.Inspection("APPLIED", ())))
    env_file = tmp_path / "offline.env"
    env_file.write_text("DATABASE_URL=postgresql://u:p@h/d\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda *args, **kwargs: connection))
    monkeypatch.setattr(runner, "inspect_schema", lambda value: next(states))

    assert runner.run(["--env-file", str(env_file), "--apply"]) == 0
    assert connection.commits == 1
    assert connection.rollbacks >= 2
    assert connection.executed == [MIGRATION.read_text(encoding="utf-8")]
    assert "MIGRATION_004_STATE = APPLIED" in capsys.readouterr().out


def test_migration_is_additive_idempotent_and_backfills_audit_timestamp():
    sql = MIGRATION.read_text(encoding="utf-8")
    upper = sql.upper()
    assert "ADD COLUMN IF NOT EXISTS UPDATED_AT TIMESTAMP" in upper
    assert "SET UPDATED_AT = COALESCE(CREATED_AT, CURRENT_TIMESTAMP)" in upper
    assert "ALTER COLUMN UPDATED_AT SET NOT NULL" in upper
    assert "CREATE TABLE IF NOT EXISTS REFRESH_TOKENS" in upper
    assert "CREATE UNIQUE INDEX IF NOT EXISTS IX_REFRESH_TOKENS_TOKEN_HASH" in upper
    for destructive in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM"):
        assert destructive not in upper


def test_runner_references_only_migration_004_and_never_selects_application_rows():
    source = SCRIPT.read_text(encoding="utf-8").upper()
    assert "004_SCHEMA_ALIGNMENT.SQL" in source
    assert "001_TOTP_ENROLLMENTS.SQL" not in source
    assert "002_AUTHENTICATOR_PLATFORM.SQL" not in source
    assert "003_PROFESSIONAL_ACCOUNTS.SQL" not in source
    assert "SELECT *" not in source
