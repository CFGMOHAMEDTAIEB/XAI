# XAI-Compress project audit

Audit date: 2026-09-20  
Repository: `C:\Users\ss\Desktop\XAI\XAI`  
Scope: local repository and toolchain only. This document does not claim production readiness.

## Executive summary

XAI-Compress is an existing multi-application monorepo. FastAPI is the authoritative identity, file, compression, share, audit, and administrator API. PostgreSQL is the Compose database. Angular is the authenticated portal, Next.js is the public site, Blazor Server is the administration UI, and two Flutter applications provide Windows desktop and Android authenticator clients. The lossless engine is a Python package with an optional Rust/PyO3 core, classical and neural codecs, Hybrid V1/V2/V3 work, and a frozen Selector V2 model.

The repository is feature-rich but the current development entry point is not a valid one-command environment. The checked-out `docker-compose.yml` has a `pgadmin` mapping outside `services`, no root `.env.example` exists although the README and startup script require it, and the current scripts neither perform the requested host-tool orchestration nor present complete health/status information. Production scanner and release-signing limitations recorded elsewhere remain unresolved and must not be inferred as fixed by local work.

The worktree was already heavily modified before this audit. Existing client, backend, migration, security, report, generated-test, and Compose changes are preserved as user work.

## Actual project tree

Generated dependency/build/cache subtrees are collapsed.

```text
XAI/
|-- apps/
|   |-- admin_dotnet/                  Blazor Server administration UI (.NET 8)
|   |-- desktop_flutter/               Flutter Windows/desktop client
|   |-- mobile_authenticator_flutter/  Flutter Android authenticator
|   |-- public_nextjs/                 Next.js 15 public site
|   `-- web_angular/                   Angular 20 authenticated portal
|-- services/
|   |-- api_fastapi/                   Authoritative FastAPI API and SQLAlchemy schema
|   |-- enterprise_spring/             Supplemental Java/Spring prototype
|   |-- realtime_node/                 Supplemental realtime Node service
|   `-- support_symfony/               Supplemental Symfony prototype
|-- engines/
|   `-- XAI-Compress/                  Python engine, optional Rust core, data, checkpoints, results
|-- analytics/XAI-Compress-Analysis-Suite/
|                                       Separate analysis utilities
|-- infrastructure/                    Keycloak/Kubernetes/monitoring/nginx/Vault material
|-- packages/protobuf_contracts/       Future internal protobuf contracts
|-- tools/admin_integration_tests/     .NET HTTP integration-test project
|-- scripts/                           Operations, migrations, validation and build scripts
|-- deployment/                        Deployment templates and operational documentation
|-- docs/                              Architecture, security, audits and integration evidence
|-- labs/                              C++/SIMD, NLP/CV/RAG and TensorFlow experiments
|-- reports/                           Requested stable report location (not present at audit time)
|-- notebooks/                         Requested notebook location (not present at audit time)
|-- releases/                          Requested local release location (not present at audit time)
|-- scratch/                           Disposable evidence and validation workspaces
|-- FINAL_REPORT/, rapport-pfe/        Graduation-project report sources/evidence
|-- docker-compose.yml                 Primary local platform definition
`-- compose.devtest.yml                Isolated backend/admin/Mailpit integration stack
```

The engine's actual directory is `engines/XAI-Compress`, not `engines/ai_compression/XAI-Compress`.

## Components, startup, ports, and dependencies

| Component | Purpose | Discovered startup/build command | Local port/URL | Principal dependencies |
| --- | --- | --- | --- | --- |
| FastAPI | Accounts, JWT/refresh, MFA/authenticator, files, compression, history, shares, admin, scanner status | Container: `python scripts/run_all_migrations.py --apply` then `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` | Compose `${API_PORT:-8000}`; dev-test `18000`; `/health`, `/docs` | Python 3.12 image; FastAPI, SQLAlchemy, psycopg, PyTorch, NumPy, Brotli, Zstandard, yara-python |
| PostgreSQL | Persistent application metadata | `docker compose up db` | Internal `db:5432`; no host publication in the audited primary Compose file | PostgreSQL 17 Alpine, named `db-data` volume |
| ClamAV | Mandatory upload/output malware scanning | `docker compose up clamav` | Internal `clamav:3310`; not published | Custom ClamAV image, named signature volume |
| Angular | Authenticated web portal | Host: `npm.cmd start`; container: nginx image after `npm.cmd run build` | `${ANGULAR_PORT:-4200}` | Angular 20, RxJS, TypeScript, Vitest dependency |
| Next.js | Public marketing, status/share metadata, downloads UI | Host: `npm.cmd run dev`; production: `npm.cmd run build`, `npm.cmd start` | `${NEXTJS_PORT:-3000}` | Next.js 15, React 19, TypeScript |
| .NET Admin | Server-side administrative console | Host: `dotnet run --project apps/admin_dotnet/AdminDotNet.csproj`; container: `dotnet AdminDotNet.dll` | `${ADMIN_PORT:-5050}` (container 8080); dev-test `15050` | .NET 8, Blazor Server, OpenID Connect package |
| Flutter Desktop | Windows/desktop compression and cloud client | `flutter run -d windows --dart-define=XAI_API_URL=...`; `flutter build windows --release` | No server port; calls API | Flutter/Dart, provider, HTTP, secure storage, file picker, window manager |
| Flutter Mobile | Android TOTP/authenticator client | `flutter run -d <device> --dart-define=XAI_API_URL=...`; `flutter build apk --release` | No server port; emulator default/API dart define | Flutter/Dart, OTP, local_auth, secure storage, HTTP |
| XAI engine | Lossless static/neural/hybrid compression, training and benchmarks | `python -m xai_compress ...`; installed console scripts `xai-compress` and `xcompress` | None | Python >=3.10, PyTorch, NumPy; optional Rust/PyO3 core |
| Mailpit | Development email capture in isolated stack | `docker compose -f compose.devtest.yml up mailpit` | UI `18025`, SMTP `11025` | Pinned Mailpit image |
| pgAdmin | Requested PostgreSQL GUI | Present but invalidly placed in current Compose; must be repaired before use | Currently hard-coded `5051` in invalid block | `dpage/pgadmin4:latest` currently unpinned |

Supplemental `enterprise_spring`, `realtime_node`, `support_symfony`, infrastructure and lab directories are not part of the currently documented primary runtime graph. They must not be silently started as production dependencies.

## Configuration names

No root `.env.example` existed at audit time, despite `README.md` and `scripts/start.ps1` referring to it. The following names are discovered from backend settings, templates, Compose, and client build configuration; values and secrets are intentionally omitted.

Backend/database/security: `APP_ENV`, `DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `JWT_SECRET`, `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS`, `SHARE_CODE_MINUTES`, `PUBLIC_BASE_URL`, `CORS_ORIGINS`, `STORAGE_PATH`, `SELECTOR_MODEL_PATH`, `MAX_UPLOAD_BYTES`, `MAX_DECOMPRESSED_BYTES`, `MAX_HEAVY_REQUESTS`, `MIN_FREE_DISK_BYTES`, `UPLOAD_IDLE_TIMEOUT`, `UPLOAD_TOTAL_TIMEOUT`, `CLAMAV_HOST`, `CLAMAV_PORT`, `SECURITY_SCAN_REQUIRED`, `SECURITY_SCAN_TIMEOUT`, `YARA_RULES_PATH`, `ADMIN_EMAILS`.

Email/account: `EMAIL_PROVIDER`, `ACCOUNT_VERIFICATION_MINUTES`, `VERIFICATION_RESEND_SECONDS`, `VERIFICATION_MAX_ATTEMPTS`, `PASSWORD_RESET_TOKEN_MINUTES`, `PHONE_VERIFICATION_REQUIRED`, `SMS_PROVIDER`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_FROM_NAME`, `SMTP_SECURITY`, `SMTP_TIMEOUT_SECONDS`, `SMTP_MAX_ATTACHMENT_BYTES`.

Bootstrap/demo: `XAI_SEED_ADMIN`, `XAI_SEED_ADMIN_EMAIL`, `XAI_SEED_ADMIN_PASSWORD`. The requested `XAI_DEMO_WEB_EMAIL`, `XAI_DEMO_WEB_PASSWORD`, `XAI_DEMO_DESKTOP_EMAIL`, and `XAI_DEMO_DESKTOP_PASSWORD` did not yet have an implementation at audit time.

Compose/UI/build: `API_BIND_ADDRESS`, `API_PORT`, `ANGULAR_PORT`, `NEXTJS_PORT`, `ADMIN_PORT`, `PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_API_URL`, `INTERNAL_API_URL`, `XAI_API_URL`, `PORT`, `PGADMIN_DEFAULT_EMAIL`, `PGADMIN_DEFAULT_PASSWORD`, `PGADMIN_PORT`, `XAI_ANDROID_KEYSTORE`, `XAI_ANDROID_STORE_PASSWORD`, `XAI_ANDROID_KEY_ALIAS`, `XAI_ANDROID_KEY_PASSWORD`, `XAI_ALLOW_DEBUG_SIGNING`.

## Database and migrations

SQLAlchemy 2 models in `services/api_fastapi/app/models.py` define these actual tables:

`users`, `totp_enrollments`, `files`, `share_codes`, `audit_events`, `account_verification_challenges`, `refresh_tokens`, `authenticator_devices`, `auth_challenges`, `auth_events`, `recovery_codes`, and `auth_policies`.

Versioned additive SQL files exist in `services/api_fastapi/migrations/000_initial_schema.sql` through `005_audit_event_invariant.sql`. `scripts/run_all_migrations.py` is copied into the backend image and invoked before Uvicorn. It maintains migration/checksum state and has tests covering fresh, partial, repeated, checksum-mismatch, concurrency, and rollback behavior. This is a custom runner, not Alembic. Earlier documentation saying that no versioned runner exists is stale.

The known `audit_events.updated_at` alignment is represented in both the model and migration series. The database must never be reset to resolve drift; the requested schema checker should use the runner's check-only behavior and catalog inspection.

## API surface

The backend exposes 48 discovered route declarations across `main.py`, `account.py`, `mfa.py`, and `authenticator.py`. Major groups are:

- health/status: `/health`, `/public/status`;
- registration/session: `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`;
- verification/password: `/auth/verification/*`, `/auth/password/*`;
- TOTP and authenticator: `/auth/totp/*`, `/auth/authenticator/*`, `/auth/devices*`, `/auth/challenges*`, `/auth/history`, `/auth/recovery-codes`;
- files/compression: `/files`, `/files/{file_id}/download`, `/compression/jobs`, `/compression/decompress`, `/history`;
- sharing: `/shares`, `/shares/{share_id}/revoke`, `/shares/redeem`, `/shares/download`, `/public/shares/{code}`;
- administration: `/admin/stats`, `/admin/users*`, `/admin/jobs`, `/admin/audit`, `/admin/security/scanner`, `/admin/email/configuration`, `/admin/authenticator/*`.

The normal compression path is fail-closed: bytes are released only after ClamAV and YARA are clean, the engine round trip completes, and integrity is verified.

## Tests discovered

Static source counting (not execution) found approximately 124 backend pytest tests, 146 engine pytest tests, 39 desktop Flutter test declarations, 22 mobile Flutter test declarations, nine Next.js Node test declarations, and one Angular `*.spec.ts`. A separate .NET project exists at `tools/admin_integration_tests/AdminIntegrationTests.csproj`. Counts are discovery aids and may differ from framework collection because of parameterization/skips.

Relevant commands:

```powershell
python -m pytest services/api_fastapi/tests -q
Push-Location engines/XAI-Compress; python -m pytest -q; Pop-Location
Push-Location apps/web_angular; npm.cmd test; Pop-Location
Push-Location apps/public_nextjs; npm.cmd run lint; npm.cmd run typecheck; node --test tests/*.test.mjs; Pop-Location
Push-Location apps/desktop_flutter; flutter test; Pop-Location
Push-Location apps/mobile_authenticator_flutter; flutter test; Pop-Location
dotnet test tools/admin_integration_tests/AdminIntegrationTests.csproj
```

Tests that need Docker daemons, scanner signatures, network/provider access, a display, a physical Android device, signing material, or production credentials must be reported separately as integration/device/external tests rather than merged with unit counts.

## Engine data, checkpoints, and benchmark evidence

The engine contains real GRU, neural-lossless/lossy, model-search, selector, and Selector V2 checkpoints/metrics. Examples include `gru_smoke.pt`, `gru_hq_v1.pt`, `gru_v2_hq.pt`, phase I/J checkpoints, `kaggle/best.pt`, `neural_lossless_v2/best.pt`, and `selector_v2/best.json`. The backend image copies only the frozen Selector V2 model and engine source/configuration.

Historical and current benchmark material exists under `engines/XAI-Compress/results`, including `final_analysis`, `final_project`, `historical_pre_140`, `hybrid_ai`, `hybrid_v2`, and `hybrid_v3`. The Hybrid V3 directory contains `benchmark.csv`, `benchmark_manifest.csv`, and `benchmark_summary.json`. These files must be provenance-checked before the notebook calls any run authoritative; pytest scratch trees and imported candidate trees are not scientific evidence.

## Build and release mechanisms

- Android and Windows release orchestration exists in `scripts/build_production.ps1`. It requires an HTTPS backend health gate; Android release signing is mandatory unless an explicit test-only debug-signing switch is used. Windows output is a folder ZIP and is explicitly unsigned.
- Flutter versions are `0.1.0+1` in both `pubspec.yaml` files.
- The Python engine is packageable from `pyproject.toml` as `xai-compress` version `0.2.0` with console entry points. This is a Python CLI package, not a native executable.
- .NET uses `dotnet publish -c Release`; several generated publish trees already exist under `apps/admin_dotnet/artifacts`.
- Angular and Next.js have Docker multi-stage production builds.
- The public download page and `apps/public_nextjs/lib/releases.json` already exist, but its existing policy accepts only approved production metadata and intentionally rejects test/unsigned/unverified artifacts. The requested local `releases/manifest.json` integration is not yet present.
- No trustworthy public release may be marked signed without certificate verification and no APK may be marked production-ready while it carries the Android Debug certificate.

## Generated, duplicate, dead, and uncertain material

| Path/pattern | Classification | Observation |
| --- | --- | --- |
| `.venv/`, `services/api_fastapi/.venv/`, `node_modules/` | Generated, safe candidate | Re-creatable dependency environments; very large local footprint |
| `**/__pycache__/`, `.pytest_cache/`, engine pytest temp trees | Generated, safe candidate | Test/interpreter caches; several paths have ACL/access anomalies |
| Angular `dist/`, Next `.next/`, Flutter `build/`, .NET `bin/` and `obj/` | Generated, safe candidate | Re-creatable build output unless referenced as release evidence |
| `.tmp/`, most `scratch/*` | Mixed | Many logs/rendered pages/test basetemps are generated, but some folders contain explicit audit evidence; require path-level review |
| `apps/admin_dotnet/artifacts/ui-publish*` | Duplicate generated output | Nested/repeated publish trees are evident; retain until release references are checked |
| `engines/XAI-Compress/results/pytest-*` and `results/hybrid_v3/tmp` | Generated test evidence | Usually disposable, but some are tracked and the dirty worktree already records deletions; do not remove blindly |
| `engines/XAI-Compress/results/model_search/imports` | Research provenance | Large/duplicated source snapshots; REVIEW_REQUIRED, not automatically removable |
| checkpoints, corpus manifests, benchmark CSV/JSON, `FINAL_REPORT` evidence | Reproducibility evidence | Must not be deleted by cleanup |
| `services/api_fastapi/xai_platform.db` | Local database artifact | May contain local user state; REVIEW_REQUIRED and never automatically deleted |
| supplemental services/labs/infrastructure | Potentially inactive source | Not part of primary runtime, but source/prototypes are not safe cleanup targets |

## Missing dependencies and local tool observations

Docker 29.7.2, Docker Compose 5.4.0, Python 3.14.7, and Node 24.19.0 were found. PowerShell's execution policy blocks `npm.ps1`, so repository scripts should invoke `npm.cmd` on Windows. Docker emitted a read-access warning for the user's Docker config in this sandbox. Flutter, .NET, Rust, and Cargo checks were interrupted by the `npm.ps1` error and require independent checks in the implementation phase. The backend image deliberately uses Python 3.12, avoiding assumptions that every dependency supports host Python 3.14.

## Blockers and inconsistencies

1. `docker-compose.yml` is structurally invalid because `pgadmin` is outside `services`.
2. Root `.env.example` is missing while the README/start script assumes it exists.
3. pgAdmin currently contains committed literal development credentials, has no named data volume, and uses an unpinned image tag.
4. The current `start.ps1` starts only Compose, creates `.env` from a missing template, waits only for hard-coded port 8000, and does not coordinate host Flutter or the requested runtime PID/log directory.
5. Current `status.ps1` and `stop.ps1` are minimal Compose wrappers and do not implement the required service/health table or project-owned host-process shutdown.
6. PostgreSQL has no published host port in primary Compose, which prevents direct host GUI/CLI access; pgAdmin can still use internal `db:5432` after repair.
7. No requested demo-user seed script, API-level two-user share demo, stable `reports/` outputs, scientific notebook, master `xai.ps1`, or local release manifest exists yet.
8. Angular's package declares Vitest but prior evidence reports a broken/missing test target; this must be reverified rather than counted as passing.
9. Production scanner readiness, real phone startup, Android/Windows signing, and clean-PC portability remain external blockers documented in `scratch/production-blockers/report.md`.
10. The repository contains large generated and tracked test-output trees plus permission-denied/stale junction-like paths; cleanup must be conservative and explicit.

## Security observations

- The backend requires a nonempty `JWT_SECRET` outside development and hides secret fields from settings representation.
- Password hashing, token hashing/rotation, MFA state, authorization checks, and recipient-bound shares already exist; demo users must use the same service logic.
- ClamAV plus YARA scanning is mandatory and fail-closed. No launcher/demo may disable `SECURITY_SCAN_REQUIRED` or bypass either component.
- The Compose database and JWT values are required from an ignored local environment. The new root template must contain placeholders only.
- pgAdmin must use separate local-only credentials from environment variables, bind to loopback, and never reuse production credentials.
- Existing production evidence says scanner availability is degraded and signing is absent/test-only. Local passes cannot change those classifications.
- A full secret-history audit was not performed. No secret values were printed during this audit.

## Audit conclusion

The architecture is coherent enough to support the requested integrated local workflow without replacing core implementations. The safest path is to repair and validate Compose, add placeholder-only local configuration, build project-owned launch/status/health controls around the existing components, reuse the custom migration runner, add development-only seeding and API-contract E2E, generate release metadata only from real files, and derive the notebook exclusively from checked-in checkpoints and benchmark evidence. Generated cleanup should remain narrowly scoped because the dirty worktree and research evidence make broad deletion unsafe.
