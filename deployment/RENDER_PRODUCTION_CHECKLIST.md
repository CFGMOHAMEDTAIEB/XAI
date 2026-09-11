# Render production readiness checklist

This runbook is preparation only. It must not be used to deploy, send email, run
migrations, or change credentials without operator approval.

## Required Render services

```text
Vercel public Next.js ─┐
Vercel Angular portal ─┼──> Render FastAPI API ──> Render PostgreSQL
Render .NET admin ─────┘             │
                                    ├──> Render private ClamAV:3310
                                    └──> Persistent Disk mounted at /data

YARA production rules remain in the FastAPI image at /app/security/yara/production.
```

The API, PostgreSQL, and private ClamAV service must be in the same Render
workspace and region. The current file/artifact design supports one API instance
with its persistent disk. Multiple API replicas are unsafe: file records contain
absolute paths to artifacts on a local disk that is not shared between replicas.

## Render API environment contract

Set these explicit baseline variables in the FastAPI Render service:

- `APP_ENV=production`
- `DATABASE_URL` — PostgreSQL psycopg URL; rotate before use.
- `JWT_SECRET` — new random server secret of at least 32 characters; rotate before use.
- `ACCESS_TOKEN_MINUTES`
- `REFRESH_TOKEN_DAYS`
- `SHARE_CODE_MINUTES`
- `EMAIL_PROVIDER=brevo`
- `BREVO_API_KEY` — rotated transactional API key.
- `BREVO_SENDER_EMAIL`
- `BREVO_SENDER_NAME`
- `CLAMAV_HOST` — the actual Render private hostname, without a scheme or port.
- `CLAMAV_PORT=3310`
- `SECURITY_SCAN_REQUIRED=true`
- `SECURITY_SCAN_TIMEOUT`
- `YARA_RULES_PATH=/app/security/yara/production`
- `STORAGE_PATH=/data`
- `CORS_ORIGINS` — exact, comma-separated HTTPS browser origins.
- `PUBLIC_BASE_URL`
- `SELECTOR_MODEL_PATH=/opt/xai-compress/checkpoints/selector_v2/best.json`
- `MAX_UPLOAD_BYTES`, `MAX_DECOMPRESSED_BYTES`, `MAX_HEAVY_REQUESTS`,
  `MIN_FREE_DISK_BYTES`, `UPLOAD_IDLE_TIMEOUT`, and `UPLOAD_TOTAL_TIMEOUT`.

With `EMAIL_PROVIDER=brevo`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
`SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_FROM_NAME`, and `SMTP_SECURITY` are not used
for delivery. `RESEND_API_KEY` and `RESEND_FROM_EMAIL` are only used when Resend
is selected. Do not configure bootstrap variables during normal runtime.

No additional environment variables are required by QR enrollment, TOTP, device
registration, Ed25519 public-key verification, number matching, recovery codes,
or authentication history. Device private keys remain exclusively on devices.
There is no configured push provider.

## Credential rotation

Before any deployment, rotate `BREVO_API_KEY`, `DATABASE_URL`, and `JWT_SECRET`.
If bootstrap credentials have ever been enabled or exposed, rotate and then remove
`XAI_SEED_ADMIN_PASSWORD`. Update the rotated values only in the corresponding
Render secret store and restart/redeploy the API after each relevant change.

Rotating `JWT_SECRET` invalidates all currently issued access tokens. Existing
passwords, TOTP factors, device registrations, recovery-code hashes, and refresh
token hashes are not changed by that rotation; users will need to sign in again.
Rotating `DATABASE_URL` requires no account migration when it points at the same
database, but changing databases requires the reviewed schema/data migration.

## Database and administrator gate

Production startup does not call `Base.metadata.create_all`; it is development
only. Before migration, take a provider snapshot, inspect the current schema and
migration history, identify the existing operator account, and confirm its stored
`users.role` value. Stop if a backup, schema, operator identity, or role check is
not available.

Apply, in order, as reviewed PostgreSQL migrations:

1. `services/api_fastapi/migrations/001_totp_enrollments.sql`
2. `services/api_fastapi/migrations/002_authenticator_platform.sql`

Both scripts are additive, use `CREATE TABLE/INDEX IF NOT EXISTS`, and do not
alter existing user factors or delete data. Run them in a transaction where the
operator's migration tool supports it; stop and restore from the snapshot on an
unexpected error. Validate tables, indexes, existing login/MFA state, and stored
operator role afterward without selecting secrets.

To promote an existing operator only after the database schema is ready, set the
one-time bootstrap variables in the protected API environment and run exactly:

```sh
python -m app.scripts.create_admin --promote-existing --allow-production-bootstrap
```

The command preserves an existing password and MFA factor. Confirm `PROMOTED`,
verify an administrator-authenticated endpoint, then remove all `XAI_SEED_ADMIN*`
variables and restart the API. Do not use public registration for promotion.

## ClamAV and YARA

Deploy ClamAV as a Render **Private Service** from
`services/api_fastapi/security/clamav/Dockerfile`. Do not expose port 3310
publicly. Preserve the official entrypoint, FreshClam updates, the included
`clamdcheck.sh` health probe, and `AlertExceedsMax yes`. Configure the API with
the service's actual Connect/Internal hostname and port 3310. Allocate at least
3 GiB memory (4 GiB preferred) for signature loading, and persist
`/var/lib/clamav` where the selected Render service supports it. Confirm private
connectivity and readiness before API traffic.

The API Dockerfile copies `services/api_fastapi/security` to `/app/security`, so
the configured production rule directory is included in the image. After image
deployment, run this read-only API-shell check:

```sh
python security/diagnose_scanners.py
```

It reports allowlisted scanner configuration, ClamAV PING, rule loading, and
scanner health without dumping settings. Require both scanners operational.
Use isolated local scanner tests for clean, detection, unavailable/fail-closed,
and decompressed-output coverage; do not add synthetic test rules to production.
The production acceptance test must include one authenticated clean upload and
decompression round trip, inspect both scanner records, and stop on any scanner
unavailable result.

## Storage and XAIC durability

Attach a Render Persistent Disk to the single API instance at `/data`. The image
runs as UID/GID 10001 and creates `/data` during image build; verify the mounted
disk is writable by that runtime user. Size the disk for retained `.xaic` files,
temporary upload/decompression workspaces, and operating headroom; the repository
does not define a universal minimum capacity. Container-local storage is not
durable and is unacceptable for this design.

Compression keeps verified artifacts and their database `artifact_path` values
for file downloads, email attachment attempts, shares, and share downloads.
Original upload and round-trip verification files are removed after successful
compression. Decompression workspaces are removed by the response background task.
Therefore persistent artifacts and their paths must survive restarts/deploys.

## Brevo controlled validation

Do not run this until secrets are rotated and the sender is verified. Use one
operator-controlled recipient and one MFA or recovery-code event. Confirm provider
acceptance and mailbox delivery, inspect only sanitized application logs, verify
retry/error behavior with no provider body disclosed, and record no secret values.
Brevo HTTPS delivery uses `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, and
`BREVO_SENDER_NAME`; it does not use legacy SMTP variables. Exact `.xaic`
attachment delivery remains blocked until provider format support is verified.

## Browser origins and public URLs

The repository's confirmed browser origins are the public Next.js site and Angular
portal origins. The .NET admin makes server-side API calls, so its own browser
origin does not require CORS access. Keep `CORS_ORIGINS` exact HTTPS origins with
no wildcard. `PUBLIC_BASE_URL` is currently a FastAPI settings field but has no
runtime consumer. `PUBLIC_SITE_URL` is not a FastAPI setting; it is legacy in the
API Render environment and must not be used as a substitute for frontend-specific
deployment variables.

## Release and rollout gates

Android production signing requires operator-owned `XAI_ANDROID_KEYSTORE`,
`XAI_ANDROID_STORE_PASSWORD`, `XAI_ANDROID_KEY_ALIAS`, and
`XAI_ANDROID_KEY_PASSWORD`; debug signing is not a production artifact. The
Windows release is currently an unsigned ZIP and requires a genuine code-signing
certificate/service before production distribution. iOS signing/distribution is
not configured in this repository.

Roll out only in this order: rotate secrets; update protected Render settings;
confirm `APP_ENV`; snapshot and inspect PostgreSQL; verify/promote the operator;
apply migrations; attach the disk; provision private ClamAV; verify YARA image
contents; verify Brevo sender; validate the API environment; deploy the API; run
health/scanner checks; deploy frontend configuration; run MFA/scanner/admin E2E;
then begin release signing work. Production push remains blocked until Android/iOS
provider credentials, device-token registration, provider abstraction, delivery,
and receipt handling are implemented and verified.
