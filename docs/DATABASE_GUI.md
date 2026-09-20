# Local PostgreSQL administration with pgAdmin

This guide is for the Docker Compose development environment only. It does not use or expose production credentials.

## Open and sign in

Run `./scripts/start-all.ps1`, then open `http://localhost:5051` (or the `PGADMIN_PORT` value from the ignored root `.env`). Sign in with `PGADMIN_DEFAULT_EMAIL` and `PGADMIN_DEFAULT_PASSWORD` from that local file. Do not reuse an application, Windows, or production password.

pgAdmin data is retained in the named Docker volume `pgadmin-data`. Ordinary `docker compose down` does not remove it.

## Register the PostgreSQL server

The first time only:

1. Choose **Add New Server**.
2. On **General**, use a local label such as `XAI Local`.
3. On **Connection**, set host name/address to `db` and port to `5432`.
4. Set maintenance database to the `POSTGRES_DB` value from the ignored `.env` (default template: `xai`).
5. Set username and password to the local `POSTGRES_USER` and `POSTGRES_PASSWORD` values.
6. Saving the password is optional. It stays in the local pgAdmin volume; never enter production credentials in this development instance.

`db:5432` is the Compose-network address. Host tools may instead connect to `127.0.0.1` and `POSTGRES_PORT` (default `15432`).

## Inspect the schema safely

Expand **Servers → XAI Local → Databases → xai → Schemas → public**. Under **Tables**, the current application schema includes:

- `users`
- `totp_enrollments`
- `files`
- `share_codes`
- `audit_events`
- `account_verification_challenges`
- `refresh_tokens`
- `authenticator_devices`
- `auth_challenges`
- `auth_events`
- `recovery_codes`
- `auth_policies`
- `schema_migrations`

Expand a table's **Columns**, **Constraints**, and **Indexes** nodes to inspect structure. To inspect a small number of rows, right-click the table and choose **View/Edit Data → First 100 Rows**. Treat password hashes, token hashes, MFA secrets, verification challenges, and device material as sensitive even in development: do not copy them into screenshots or reports.

Prefer read-only SQL such as:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

Do not edit authentication/security rows directly. Create users and exercise state transitions through the application/API scripts.

## Migrations and drift checks

SQL migrations live in `services/api_fastapi/migrations`. The custom runner `scripts/run_all_migrations.py` records filename and SHA-256 checksums in `schema_migrations`, uses a PostgreSQL advisory lock, applies migrations transactionally, and validates required tables/columns/indexes. Backend startup applies pending additive migrations before Uvicorn starts.

Run the non-destructive verification command at any time:

```powershell
./scripts/check-db-schema.ps1
```

The check reports pending migrations, modified historical migration files, or required-object drift and exits nonzero without changing data. Never drop/recreate the database or remove the `db-data` volume to resolve migration drift.
