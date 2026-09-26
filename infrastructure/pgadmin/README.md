# pgAdmin local registration

The Compose service imports `servers.json` for the existing pgAdmin user and
registers the PostgreSQL service as **XAI-Compress** at `db:5432`, maintenance
database `xai`, user `xai`, and SSL mode `prefer`.

The database password is never stored in the tracked JSON file. At container
startup Compose writes an owner-only pgpass file inside the existing pgAdmin
data volume from the ignored local `POSTGRES_PASSWORD` setting.

For report-safe PFE browsing, open the Query Tool on database `xai` and use
[`PFE_SAFE_QUERIES.sql`](PFE_SAFE_QUERIES.sql). These queries select only safe
columns. Do not capture **View/Edit Data → All Rows** for tables containing
password hashes, token hashes, TOTP material, verification/reset codes,
recovery codes, or share-code hashes.
