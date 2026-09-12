"""Read-only production authenticator schema check; never prints connection data."""
from pathlib import Path
import json
import psycopg

EXPECTED = {
    "001": {"totp_enrollments": {"user_id", "enrollment_id", "secret", "code_hash", "expires_at", "code_expires_at", "disclosed", "attempts", "totp_attempts", "last_sent_at", "send_window_at", "send_count"}},
    "002": {
        "authenticator_devices": {"id", "device_id", "user_id", "public_key", "platform", "app_version", "status", "registered_at", "last_activity_at"},
        "auth_challenges": {"id", "challenge_id", "user_id", "device_id", "nonce", "number_hash", "application", "request_context", "status", "created_at", "expires_at", "completed_at"},
        "auth_events": {"id", "user_id", "device_id", "event_type", "result", "application", "details", "created_at"},
        "recovery_codes": {"id", "user_id", "code_hash", "created_at", "used_at"},
        "auth_policies": {"id", "scope", "mfa_required", "totp_allowed", "push_allowed", "number_matching_required", "challenge_seconds", "session_minutes"},
    },
}


def configured_dsn() -> str | None:
    for raw in Path(".env.render.production").read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and line.split("=", 1)[0].strip() == "DATABASE_URL":
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            return value.replace("postgresql+psycopg://", "postgresql://", 1)
    return None


def main() -> None:
    dsn = configured_dsn()
    if not dsn:
        print(json.dumps({"connection": "BLOCKED", "reason": "DATABASE_URL_NOT_CONFIGURED"}))
        return
    try:
        with psycopg.connect(dsn, connect_timeout=12) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()")
                tables = {row[0] for row in cursor.fetchall()}
                cursor.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=current_schema()")
                columns: dict[str, set[str]] = {}
                for table, column in cursor.fetchall():
                    columns.setdefault(table, set()).add(column)
                cursor.execute("SELECT tablename,indexname FROM pg_indexes WHERE schemaname=current_schema()")
                indexes: dict[str, set[str]] = {}
                for table, index in cursor.fetchall():
                    indexes.setdefault(table, set()).add(index)
                cursor.execute("SELECT table_name,constraint_name,constraint_type FROM information_schema.table_constraints WHERE table_schema=current_schema()")
                constraints: dict[str, list[dict[str, str]]] = {}
                for table, name, kind in cursor.fetchall():
                    constraints.setdefault(table, []).append({"name": name, "type": kind})
                history = sorted(tables & {"alembic_version", "schema_migrations", "migrations", "migration_history"})
                result: dict[str, object] = {"connection": "READY", "history_tables": history, "migrations": {}}
                migrations = result["migrations"]
                assert isinstance(migrations, dict)
                for migration, specification in EXPECTED.items():
                    missing_tables = sorted(set(specification) - tables)
                    missing_columns = {table: sorted(required - columns.get(table, set())) for table, required in specification.items() if table in tables and required - columns.get(table, set())}
                    present = sum(table in tables for table in specification)
                    status = "APPLIED" if not missing_tables and not missing_columns else ("MISSING" if present == 0 else "PARTIAL")
                    migrations[migration] = {"status": status, "missing_tables": missing_tables, "missing_columns": missing_columns,
                        "indexes": {table: sorted(indexes.get(table, set())) for table in specification if table in tables},
                        "constraints": {table: constraints.get(table, []) for table in specification if table in tables}}
                print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(json.dumps({"connection": "BLOCKED", "reason": type(error).__name__}))


if __name__ == "__main__":
    main()
