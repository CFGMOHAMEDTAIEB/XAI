"""Safety-focused unit tests for the one-shot migration 003 runner."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "run_migration_003.py"
SPEC = importlib.util.spec_from_file_location("run_migration_003", SCRIPT)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_reads_only_database_url_without_changing_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "unchanged")
    env_file = tmp_path / "production.env"
    env_file.write_text(
        "IGNORED=secret\nexport DATABASE_URL='postgresql://user:password@host/db?sslmode=require'\n",
        encoding="utf-8",
    )

    assert runner.read_database_url(env_file) == "postgresql://user:password@host/db?sslmode=require"
    assert os.environ["DATABASE_URL"] == "unchanged"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("postgresql+psycopg://user:pass@host/db", "postgresql://user:pass@host/db"),
        ("postgresql://user:pass@host/db", "postgresql://user:pass@host/db"),
        ("postgres://user:pass@host/db", "postgres://user:pass@host/db"),
    ],
)
def test_normalizes_accepted_database_schemes(source, expected):
    assert runner.normalize_database_url(source) == expected


def test_rejects_unsupported_database_scheme():
    with pytest.raises(runner.UnsupportedDatabaseScheme):
        runner.normalize_database_url("mysql://user:pass@host/db")


@pytest.mark.parametrize("arguments", [[], ["--env-file", "x"], ["--env-file", "x", "--apply", "--check-only"]])
def test_requires_exactly_one_explicit_mode(arguments):
    with pytest.raises(ValueError):
        runner.parse_args(arguments)


def test_failure_output_never_includes_exception_or_database_url(tmp_path, capsys, monkeypatch):
    secret = "postgresql://private-user:private-password@private-host/private-db"
    env_file = tmp_path / "production.env"
    env_file.write_text(f"DATABASE_URL={secret}\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(secret))))

    assert runner.run(["--env-file", str(env_file), "--check-only"]) == 1
    output = capsys.readouterr()
    assert output.out == "FAIL: DB_CONNECT_FAIL exception=RuntimeError\n"
    assert output.err == ""
    assert secret not in output.out


def test_runner_references_only_migration_003():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "003_professional_accounts.sql" in source
    assert "001_totp_enrollments.sql" not in source
    assert "002_authenticator_platform.sql" not in source
    assert "SELECT EMAIL" not in source.upper()


class MetadataConnection:
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    def cursor(self):
        return self.Cursor()


def install_metadata(monkeypatch, *, users=None, table=False, challenges=None, constraints=None, indexes=None):
    monkeypatch.setattr(runner, "_columns", lambda cursor, name: (users or {}) if name == "users" else (challenges or {}))
    monkeypatch.setattr(runner, "_table_exists", lambda cursor, name: table)
    monkeypatch.setattr(runner, "_constraints", lambda cursor: constraints or {})
    monkeypatch.setattr(runner, "_indexes", lambda cursor, table_name: (indexes or {}).get(table_name, {}))


def complete_constraints():
    return {
        "account_verification_challenges_pkey": ("p", "PRIMARY KEY (id)"),
        "account_verification_challenges_user_id_fkey": ("f", "FOREIGN KEY (user_id) REFERENCES users(id)"),
        "account_verification_challenges_reset_token_hash_key": ("u", "UNIQUE (reset_token_hash)"),
        "ck_verification_channel": ("c", "CHECK channel IN ('email', 'phone')"),
        "ck_verification_purpose": (
            "c",
            "CHECK purpose IN ('ACCOUNT_EMAIL_VERIFY', 'ACCOUNT_PHONE_VERIFY', 'PASSWORD_RESET')",
        ),
    }


def complete_indexes():
    return {
        "users": {
            "uq_users_phone_number": "CREATE UNIQUE INDEX uq_users_phone_number ON users (phone_number) WHERE phone_number IS NOT NULL",
            "ix_users_account_status": "CREATE INDEX ix_users_account_status ON users (account_status)",
        },
        "account_verification_challenges": {
            "ix_account_verification_user": "CREATE INDEX ix_account_verification_user ON account_verification_challenges (user_id)",
            "ix_account_verification_purpose": "CREATE INDEX ix_account_verification_purpose ON account_verification_challenges (purpose)",
            "ix_account_verification_expires": "CREATE INDEX ix_account_verification_expires ON account_verification_challenges (expires_at)",
        },
    }


def test_schema_inspection_completely_unapplied(monkeypatch):
    install_metadata(monkeypatch)
    result = runner.inspect_schema(MetadataConnection())
    assert result.state == "NOT_APPLIED"
    assert "users.full_name" in result.missing
    assert "table.account_verification_challenges" in result.missing


def test_schema_inspection_fully_applied(monkeypatch):
    install_metadata(
        monkeypatch,
        users=runner.USER_COLUMNS,
        table=True,
        challenges=runner.CHALLENGE_COLUMNS,
        constraints=complete_constraints(),
        indexes=complete_indexes(),
    )
    result = runner.inspect_schema(MetadataConnection())
    assert result.state == "APPLIED"
    assert result.missing == ()


def test_schema_inspection_partially_applied(monkeypatch):
    users = {"full_name": runner.USER_COLUMNS["full_name"]}
    install_metadata(monkeypatch, users=users)
    result = runner.inspect_schema(MetadataConnection())
    assert result.state == "PARTIAL"
    assert "users.full_name" not in result.missing
    assert "users.phone_number" in result.missing


def test_existing_users_table_without_migration_columns_is_not_applied(monkeypatch):
    install_metadata(monkeypatch, users={})
    result = runner.inspect_schema(MetadataConnection())
    assert result.state == "NOT_APPLIED"
    assert all(f"users.{name}" in result.missing for name in runner.USER_COLUMNS)


def test_metadata_query_failure_has_safe_diagnostics(tmp_path, capsys, monkeypatch):
    class MetadataError(Exception):
        sqlstate = "42501"

    class Connection:
        def rollback(self):
            pass

        def close(self):
            pass

    env_file = tmp_path / "production.env"
    env_file.write_text("DATABASE_URL=postgresql://private:secret@host/db\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda *args, **kwargs: Connection()))
    monkeypatch.setattr(runner, "inspect_schema", lambda connection: (_ for _ in ()).throw(MetadataError("secret")))

    assert runner.run(["--env-file", str(env_file), "--check-only"]) == 1
    output = capsys.readouterr().out
    assert output == (
        "DATABASE_CONNECTION = PASS\n"
        "FAIL: SCHEMA_CHECK_FAIL\n"
        "ERROR_STAGE = SCHEMA_CHECK\n"
        "ERROR_TYPE = MetadataError\n"
        "SQLSTATE = 42501\n"
    )
    assert "secret" not in output
