"""Safely check or apply PostgreSQL migration 004, and no other migration."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Any, NamedTuple


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "services" / "api_fastapi" / "migrations" / "004_schema_alignment.sql"

COLUMN_SPECS = {
    "users": {"role": ("character varying", 32, False)},
    "files": {
        "source_path": ("character varying", 1024, True),
        "artifact_path": ("character varying", 1024, True),
        "integrity_verified": ("boolean", None, False),
        "status": ("character varying", 32, False),
    },
    "audit_events": {"updated_at": ("timestamp without time zone", None, False)},
    "refresh_tokens": {
        "id": ("integer", None, False),
        "user_id": ("integer", None, False),
        "token_hash": ("character varying", 64, False),
        "expires_at": ("timestamp without time zone", None, False),
        "revoked": ("boolean", None, False),
        "created_at": ("timestamp without time zone", None, False),
    },
}

INDEX_SPECS = {
    "ix_refresh_tokens_user_id": (False, "user_id"),
    "ix_refresh_tokens_token_hash": (True, "token_hash"),
}

CONSTRAINT_SPECS = {
    "refresh_tokens_pkey": ("p", ("primarykey(id)",)),
    "refresh_tokens_user_id_fkey": ("f", ("foreignkey(user_id)", "referencesusers(id)")),
}


class Inspection(NamedTuple):
    state: str
    missing: tuple[str, ...]


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


class UnsupportedDatabaseScheme(ValueError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeArgumentParser(add_help=False)
    parser.add_argument("--env-file", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def read_database_url(env_file: Path) -> str:
    value: str | None = None
    with env_file.open("r", encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, candidate = line.partition("=")
            if separator and key.strip() == "DATABASE_URL":
                candidate = candidate.strip()
                if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in "\"'":
                    candidate = candidate[1:-1]
                value = candidate
    if not value:
        raise ValueError("DATABASE_URL missing")
    return value


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + database_url[len("postgresql+psycopg://") :]
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        return database_url
    raise UnsupportedDatabaseScheme("unsupported database scheme")


def _safe_failure(code: str, error: BaseException | None = None) -> int:
    details = ""
    if error is not None:
        class_name = type(error).__name__
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", class_name):
            class_name = "Exception"
        details = f" exception={class_name}"
        sqlstate = getattr(error, "sqlstate", None)
        if isinstance(sqlstate, str) and re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
            details += f" sqlstate={sqlstate}"
    print(f"FAIL: {code}{details}")
    return 1


def _safe_rollback(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _safe_close(connection: Any) -> None:
    try:
        connection.close()
    except Exception:
        pass


def _columns(cursor: Any, table: str) -> dict[str, tuple[str, int | None, bool]]:
    cursor.execute(
        """
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = %s
        """,
        (table,),
    )
    return {name: (kind, length, nullable == "YES") for name, kind, length, nullable in cursor.fetchall()}


def _table_exists(cursor: Any, table: str) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_name = %s
              AND table_type = 'BASE TABLE'
        )
        """,
        (table,),
    )
    row = cursor.fetchone()
    return bool(row and row[0])


def _indexes(cursor: Any) -> dict[str, str]:
    cursor.execute(
        """
        SELECT indexname, indexdef FROM pg_catalog.pg_indexes
        WHERE schemaname = current_schema() AND tablename = 'refresh_tokens'
        """
    )
    return {name: definition for name, definition in cursor.fetchall()}


def _constraints(cursor: Any) -> dict[str, tuple[str, str]]:
    cursor.execute(
        """
        SELECT c.conname, c.contype, pg_get_constraintdef(c.oid)
        FROM pg_catalog.pg_constraint c
        JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = current_schema() AND t.relname = 'refresh_tokens'
        """
    )
    return {name: (kind, definition) for name, kind, definition in cursor.fetchall()}


def _normalize(definition: str) -> str:
    return re.sub(r'[\s"]+', "", definition).lower()


def inspect_schema(connection: Any) -> Inspection:
    missing: list[str] = []
    present = 0
    with connection.cursor() as cursor:
        refresh_exists = _table_exists(cursor, "refresh_tokens")
        for table, expected in COLUMN_SPECS.items():
            actual = _columns(cursor, table)
            for name, spec in expected.items():
                if actual.get(name) == spec:
                    present += 1
                else:
                    missing.append(f"{table}.{name}")

        if refresh_exists:
            present += 1
            indexes = _indexes(cursor)
            constraints = _constraints(cursor)
        else:
            missing.append("table.refresh_tokens")
            indexes = {}
            constraints = {}

        for name, (unique, column) in INDEX_SPECS.items():
            definition = _normalize(indexes.get(name, ""))
            valid = bool(definition) and f"({column})" in definition
            valid = valid and ("createuniqueindex" in definition) == unique
            if valid:
                present += 1
            else:
                missing.append(f"index.{name}")

        for name, (kind, tokens) in CONSTRAINT_SPECS.items():
            actual = constraints.get(name)
            if actual and actual[0] == kind and all(token in _normalize(actual[1]) for token in tokens):
                present += 1
            else:
                missing.append(f"constraint.{name}")

    state = "APPLIED" if not missing else "NOT_APPLIED" if present == 0 else "PARTIAL"
    return Inspection(state, tuple(missing))


def _print_inspection(inspection: Inspection) -> None:
    print(f"MIGRATION_004_STATE = {inspection.state}")
    for name in inspection.missing:
        print(f"MISSING_OBJECT = {name}")


def run(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        database_url = normalize_database_url(read_database_url(Path(args.env_file)))
    except UnsupportedDatabaseScheme:
        return _safe_failure("UNSUPPORTED_DB_SCHEME")
    except Exception as error:
        return _safe_failure("ENV_PARSE_FAIL", error)

    try:
        import psycopg

        connection = psycopg.connect(database_url, autocommit=False)
    except Exception as error:
        return _safe_failure("DB_CONNECT_FAIL", error)

    print("DATABASE_CONNECTION = PASS")
    try:
        try:
            inspection = inspect_schema(connection)
            connection.rollback()
        except Exception as error:
            _safe_rollback(connection)
            return _safe_failure("SCHEMA_CHECK_FAIL", error)

        if inspection.state == "APPLIED" or args.check_only:
            _print_inspection(inspection)
            return 0 if inspection.state == "APPLIED" else 1

        try:
            migration_sql = MIGRATION.read_text(encoding="utf-8")
            with connection.cursor() as cursor:
                cursor.execute(migration_sql)
            if inspect_schema(connection).state != "APPLIED":
                raise RuntimeError("metadata verification failed")
            connection.commit()
        except Exception as error:
            _safe_rollback(connection)
            return _safe_failure("MIGRATION_APPLY_FAIL", error)

        try:
            inspection = inspect_schema(connection)
            connection.rollback()
            if inspection.state != "APPLIED":
                return _safe_failure("POST_VERIFY_FAIL")
            _print_inspection(inspection)
            return 0
        except Exception as error:
            _safe_rollback(connection)
            return _safe_failure("POST_VERIFY_FAIL", error)
    finally:
        _safe_close(connection)


if __name__ == "__main__":
    sys.exit(run())
