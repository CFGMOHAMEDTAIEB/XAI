"""Discover, validate, and transactionally apply PostgreSQL SQL migrations."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
from typing import Any, NamedTuple


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = next(
    (path for path in (ROOT / "services" / "api_fastapi" / "migrations", ROOT / "migrations") if path.is_dir()),
    ROOT / "services" / "api_fastapi" / "migrations",
)
MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{3,})_[A-Za-z0-9_]+\.sql$")
LOCK_KEY = 751_004_202_609_13

TRACKING_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(32) PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

# Allows safe first adoption on databases where migrations 001-004 predate the
# tracking table. Only metadata is inspected; migration SQL is never re-run when
# all of its characteristic objects are already present.
LEGACY_OBJECTS = {
    "001": {
        "tables": {"totp_enrollments"},
        "columns": {
            ("totp_enrollments", name)
            for name in (
                "user_id", "enrollment_id", "secret", "code_hash", "expires_at", "code_expires_at",
                "disclosed", "attempts", "totp_attempts", "last_sent_at", "send_window_at", "send_count",
            )
        },
        "indexes": set(),
    },
    "002": {
        "tables": {"authenticator_devices", "auth_challenges", "auth_events", "recovery_codes", "auth_policies"},
        "columns": {
            ("authenticator_devices", "device_id"), ("authenticator_devices", "last_activity_at"),
            ("auth_challenges", "challenge_id"), ("auth_challenges", "completed_at"),
            ("auth_events", "event_type"), ("auth_events", "created_at"),
            ("recovery_codes", "code_hash"), ("auth_policies", "session_minutes"),
        },
        "indexes": {
            "ix_authenticator_devices_user_id", "ix_authenticator_devices_status",
            "ix_auth_challenges_user_id", "ix_auth_challenges_device_id", "ix_auth_challenges_status",
            "ix_auth_events_user_id", "ix_auth_events_device_id", "ix_auth_events_event_type",
            "ix_auth_events_created_at", "ix_recovery_codes_user_id",
        },
    },
    "003": {
        "tables": {"account_verification_challenges"},
        "columns": {
            ("users", "full_name"), ("users", "phone_number"), ("users", "email_verified"),
            ("users", "phone_verified"), ("users", "account_status"), ("users", "updated_at"),
            ("account_verification_challenges", "reset_token_hash"),
            ("account_verification_challenges", "last_sent_at"),
        },
        "indexes": {
            "uq_users_phone_number", "ix_users_account_status", "ix_account_verification_user",
            "ix_account_verification_purpose", "ix_account_verification_expires",
        },
    },
    "004": {
        "tables": {"refresh_tokens"},
        "columns": {
            ("users", "role"), ("files", "source_path"), ("files", "artifact_path"),
            ("files", "integrity_verified"), ("files", "status"), ("audit_events", "updated_at"),
            ("refresh_tokens", "id"), ("refresh_tokens", "user_id"),
            ("refresh_tokens", "token_hash"), ("refresh_tokens", "expires_at"),
            ("refresh_tokens", "revoked"), ("refresh_tokens", "created_at"),
        },
        "indexes": {"ix_refresh_tokens_user_id", "ix_refresh_tokens_token_hash"},
    },
}


class Migration(NamedTuple):
    version: str
    filename: str
    path: Path
    checksum: str


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


class MigrationError(Exception):
    def __init__(self, code: str, version: str | None = None):
        super().__init__(code)
        self.code = code
        self.version = version


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeArgumentParser(add_help=False)
    parser.add_argument("--env-file")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def _read_env_file(path: Path) -> str | None:
    value: str | None = None
    with path.open("r", encoding="utf-8-sig") as handle:
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
    return value


def database_url(env_file: str | None) -> str:
    value = _read_env_file(Path(env_file)) if env_file else os.environ.get("DATABASE_URL")
    if not value:
        raise MigrationError("DATABASE_URL_MISSING")
    if value.startswith("postgresql+psycopg://"):
        return "postgresql://" + value[len("postgresql+psycopg://") :]
    if value.startswith("postgresql://") or value.startswith("postgres://"):
        return value
    raise MigrationError("UNSUPPORTED_DB_SCHEME")


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations: list[Migration] = []
    numeric_versions: set[int] = set()
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() != ".sql":
            continue
        match = MIGRATION_NAME.fullmatch(path.name)
        if not match:
            raise MigrationError("INVALID_MIGRATION_FILENAME")
        version = match.group("version")
        numeric_version = int(version)
        if numeric_version in numeric_versions:
            raise MigrationError("DUPLICATE_MIGRATION_VERSION", version)
        numeric_versions.add(numeric_version)
        migrations.append(Migration(version, path.name, path, hashlib.sha256(path.read_bytes()).hexdigest()))
    if not migrations:
        raise MigrationError("NO_MIGRATIONS_FOUND")
    return sorted(migrations, key=lambda migration: int(migration.version))


def _tracking_exists(cursor: Any) -> bool:
    cursor.execute("SELECT to_regclass(current_schema() || '.schema_migrations') IS NOT NULL")
    row = cursor.fetchone()
    return bool(row and row[0])


def _applied(cursor: Any, tracking_exists: bool) -> dict[str, tuple[str, str]]:
    if not tracking_exists:
        return {}
    cursor.execute("SELECT version, filename, checksum FROM schema_migrations")
    return {version: (filename, checksum) for version, filename, checksum in cursor.fetchall()}


def _legacy_present(cursor: Any, migration: Migration) -> bool:
    required = LEGACY_OBJECTS.get(migration.version)
    if required is None:
        return False
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
    )
    tables = {row[0] for row in cursor.fetchall()}
    cursor.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema()"
    )
    columns = {(row[0], row[1]) for row in cursor.fetchall()}
    cursor.execute("SELECT indexname FROM pg_catalog.pg_indexes WHERE schemaname = current_schema()")
    indexes = {row[0] for row in cursor.fetchall()}
    return required["tables"] <= tables and required["columns"] <= columns and required["indexes"] <= indexes


def _record(cursor: Any, migration: Migration) -> None:
    cursor.execute(
        "INSERT INTO schema_migrations (version, filename, checksum) VALUES (%s, %s, %s)",
        (migration.version, migration.filename, migration.checksum),
    )


def _validate_recorded(migrations: list[Migration], applied: dict[str, tuple[str, str]]) -> None:
    by_version = {migration.version: migration for migration in migrations}
    for version, (filename, checksum) in applied.items():
        migration = by_version.get(version)
        if migration is None:
            raise MigrationError("MIGRATION_FILE_MISSING", version)
        if migration.filename != filename or migration.checksum != checksum:
            raise MigrationError("CHECKSUM_MISMATCH", version)


def migration_plan(cursor: Any, migrations: list[Migration], tracking_exists: bool) -> tuple[list[Migration], list[Migration]]:
    applied = _applied(cursor, tracking_exists)
    _validate_recorded(migrations, applied)
    baseline: list[Migration] = []
    pending: list[Migration] = []
    for migration in migrations:
        if migration.version in applied:
            continue
        if _legacy_present(cursor, migration):
            baseline.append(migration)
        else:
            pending.append(migration)
    return baseline, pending


def apply_one(connection: Any, migration: Migration, *, execute_sql: bool) -> None:
    try:
        with connection.cursor() as cursor:
            if execute_sql:
                cursor.execute(migration.path.read_text(encoding="utf-8"))
            _record(cursor, migration)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _safe_error(error: BaseException, active_version: str | None = None) -> int:
    code = error.code if isinstance(error, MigrationError) else "MIGRATION_STARTUP_FAIL"
    suffix = ""
    version = error.version if isinstance(error, MigrationError) and error.version else active_version
    if version and version.isdigit():
        suffix = f" version={version}"
    class_name = type(error).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", class_name):
        class_name = "Exception"
    sqlstate = getattr(error, "sqlstate", None)
    sqlstate = sqlstate if isinstance(sqlstate, str) and re.fullmatch(r"[0-9A-Z]{5}", sqlstate) else "N/A"
    print(f"AUTOMATIC_MIGRATIONS = FAIL code={code}{suffix}")
    print(f"ERROR_TYPE = {class_name}")
    print(f"SQLSTATE = {sqlstate}")
    return 1


def run(argv: list[str] | None = None) -> int:
    connection = None
    locked = False
    active_version = None
    try:
        args = parse_args(argv)
        migrations = discover_migrations()
        url = database_url(args.env_file)
        import psycopg

        connection = psycopg.connect(url, autocommit=False)
        with connection.cursor() as cursor:
            if args.apply:
                cursor.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
                locked = True
            tracking_exists = _tracking_exists(cursor)
            baseline, pending = migration_plan(cursor, migrations, tracking_exists)
        connection.rollback()

        if args.check_only:
            outstanding = sorted(baseline + pending, key=lambda migration: int(migration.version))
            print("DATABASE_CONNECTION = PASS")
            print(f"MIGRATIONS_TOTAL = {len(migrations)}")
            print(f"MIGRATIONS_PENDING = {len(outstanding)}")
            for migration in outstanding:
                print(f"PENDING_MIGRATION = {migration.filename}")
            print("AUTOMATIC_MIGRATIONS = PASS" if not baseline and not pending else "AUTOMATIC_MIGRATIONS = PENDING")
            return 0 if not baseline and not pending else 1

        if not tracking_exists:
            with connection.cursor() as cursor:
                cursor.execute(TRACKING_DDL)
            connection.commit()

        actions = [(migration, False) for migration in baseline] + [(migration, True) for migration in pending]
        for migration, execute_sql in sorted(actions, key=lambda action: int(action[0].version)):
            active_version = migration.version
            apply_one(connection, migration, execute_sql=execute_sql)
            status = "APPLIED" if execute_sql else "BASELINED"
            print(f"MIGRATION_{migration.version} = {status}")
            active_version = None
        print("AUTOMATIC_MIGRATIONS = PASS")
        return 0
    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        return _safe_error(error, active_version)
    finally:
        if connection is not None:
            if locked:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
                    connection.commit()
                except Exception:
                    try:
                        connection.rollback()
                    except Exception:
                        pass
            try:
                connection.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(run())
