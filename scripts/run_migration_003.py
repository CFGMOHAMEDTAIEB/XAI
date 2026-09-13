"""Safely check or apply PostgreSQL migration 003, and no other migration."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "services" / "api_fastapi" / "migrations" / "003_professional_accounts.sql"

USER_COLUMNS = {
    "full_name": ("character varying", 120, False),
    "phone_number": ("character varying", 16, True),
    "email_verified": ("boolean", None, False),
    "phone_verified": ("boolean", None, False),
    "account_status": ("character varying", 32, False),
    "updated_at": ("timestamp without time zone", None, False),
}

CHALLENGE_COLUMNS = {
    "id": ("integer", None, False),
    "user_id": ("integer", None, False),
    "channel": ("character varying", 16, False),
    "purpose": ("character varying", 40, False),
    "code_hash": ("character varying", 64, False),
    "expires_at": ("timestamp without time zone", None, False),
    "attempt_count": ("integer", None, False),
    "max_attempts": ("integer", None, False),
    "used_at": ("timestamp without time zone", None, True),
    "verified_at": ("timestamp without time zone", None, True),
    "reset_token_hash": ("character varying", 64, True),
    "reset_token_expires_at": ("timestamp without time zone", None, True),
    "created_at": ("timestamp without time zone", None, False),
    "last_sent_at": ("timestamp without time zone", None, False),
}

REQUIRED_INDEXES = {
    "users": {
        "uq_users_phone_number": (True, "phone_number", True),
        "ix_users_account_status": (False, "account_status", False),
    },
    "account_verification_challenges": {
        "ix_account_verification_user": (False, "user_id", False),
        "ix_account_verification_purpose": (False, "purpose", False),
        "ix_account_verification_expires": (False, "expires_at", False),
    },
}

REQUIRED_CONSTRAINTS = {
    "account_verification_challenges_pkey": ("p", ("primarykey(id)",)),
    "account_verification_challenges_user_id_fkey": ("f", ("foreignkey(user_id)", "referencesusers(id)")),
    "account_verification_challenges_reset_token_hash_key": ("u", ("unique(reset_token_hash)",)),
    "ck_verification_channel": ("c", ("email", "phone")),
    "ck_verification_purpose": ("c", ("account_email_verify", "account_phone_verify", "password_reset")),
}


class SchemaInspection(NamedTuple):
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
    """Read DATABASE_URL without modifying os.environ or returning other values."""
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
    """Translate only SQLAlchemy's psycopg scheme for a direct psycopg connection."""
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


def _safe_error_details(stage: str, error: BaseException) -> int:
    class_name = type(error).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", class_name):
        class_name = "Exception"
    sqlstate = getattr(error, "sqlstate", None)
    if not isinstance(sqlstate, str) or not re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
        sqlstate = "N/A"
    print(f"FAIL: {stage}_FAIL")
    print(f"ERROR_STAGE = {stage}")
    print(f"ERROR_TYPE = {class_name}")
    print(f"SQLSTATE = {sqlstate}")
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


def _constraints(cursor: Any) -> dict[str, tuple[str, str]]:
    cursor.execute(
        """
        SELECT c.conname, c.contype, pg_get_constraintdef(c.oid)
        FROM pg_catalog.pg_constraint c
        JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = current_schema()
          AND t.relname = 'account_verification_challenges'
        """
    )
    return {name: (kind, definition) for name, kind, definition in cursor.fetchall()}


def _indexes(cursor: Any, table: str) -> dict[str, str]:
    cursor.execute(
        """
        SELECT indexname, indexdef
        FROM pg_catalog.pg_indexes
        WHERE schemaname = current_schema() AND tablename = %s
        """,
        (table,),
    )
    return {name: definition for name, definition in cursor.fetchall()}


def _normalized_definition(definition: str) -> str:
    return re.sub(r'[\s"]+', "", definition).lower()


def inspect_schema(connection: Any) -> SchemaInspection:
    """Inspect catalog metadata only; missing objects are ordinary results."""
    missing: list[str] = []
    present = 0
    with connection.cursor() as cursor:
        users = _columns(cursor, "users")
        for name, spec in USER_COLUMNS.items():
            if users.get(name) == spec:
                present += 1
            else:
                missing.append(f"users.{name}")

        challenge_exists = _table_exists(cursor, "account_verification_challenges")
        if challenge_exists:
            present += 1
            challenges = _columns(cursor, "account_verification_challenges")
            for name, spec in CHALLENGE_COLUMNS.items():
                if challenges.get(name) == spec:
                    present += 1
                else:
                    missing.append(f"account_verification_challenges.{name}")
            constraints = _constraints(cursor)
        else:
            missing.append("table.account_verification_challenges")
            missing.extend(f"account_verification_challenges.{name}" for name in CHALLENGE_COLUMNS)
            constraints = {}

        for name, (kind, tokens) in REQUIRED_CONSTRAINTS.items():
            actual = constraints.get(name)
            if actual and actual[0] == kind and all(token in _normalized_definition(actual[1]) for token in tokens):
                present += 1
            else:
                missing.append(f"constraint.{name}")

        for table, expected in REQUIRED_INDEXES.items():
            actual_indexes = _indexes(cursor, table)
            for name, (unique, column, partial) in expected.items():
                definition = _normalized_definition(actual_indexes.get(name, ""))
                valid = bool(definition) and f"({column})" in definition
                valid = valid and ("createuniqueindex" in definition) == unique
                valid = valid and ("where" in definition) == partial
                if valid:
                    present += 1
                else:
                    missing.append(f"index.{name}")

    if not missing:
        state = "APPLIED"
    elif present == 0:
        state = "NOT_APPLIED"
    else:
        state = "PARTIAL"
    return SchemaInspection(state, tuple(missing))


def schema_is_present(connection: Any) -> bool:
    return inspect_schema(connection).state == "APPLIED"


def _print_inspection(inspection: SchemaInspection) -> None:
    print(f"MIGRATION_003_STATE = {inspection.state}")
    for name in inspection.missing:
        print(f"MISSING_OBJECT = {name}")


def run(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        database_url = read_database_url(Path(args.env_file))
    except Exception as error:
        return _safe_failure("ENV_PARSE_FAIL", error)

    try:
        database_url = normalize_database_url(database_url)
    except UnsupportedDatabaseScheme:
        return _safe_failure("UNSUPPORTED_DB_SCHEME")

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
            return _safe_error_details("SCHEMA_CHECK", error)

        if inspection.state == "APPLIED":
            _print_inspection(inspection)
            return 0

        if args.check_only:
            _print_inspection(inspection)
            return 1

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
            if inspection.state != "APPLIED":
                _safe_rollback(connection)
                return _safe_failure("POST_VERIFY_FAIL")
            connection.rollback()
            _print_inspection(inspection)
            return 0
        except Exception as error:
            _safe_rollback(connection)
            return _safe_failure("POST_VERIFY_FAIL", error)
    finally:
        _safe_close(connection)


if __name__ == "__main__":
    sys.exit(run())
