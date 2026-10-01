# Repository Cleanup Report

Completed: 2026-09-26. Scope: approved safe filesystem cleanup only. No database row, Docker volume, SQLite database, release artifact, evidence item, scientific dataset, checkpoint, model, benchmark result, source file, migration, `.tmp` content, or `.xai-runtime` content was deleted.

## Result

Safe cleanup completed partially. All unlocked, high-confidence generated targets were removed. Ten approved generated/test roots remain partially present because Windows processes hold binaries open or their historical basetemps have restrictive ACLs. Processes were not terminated and ACLs were not weakened.

| Measure | Result |
| --- | ---: |
| Files removed | 81,197 |
| Directories removed | 8,982 |
| Exact logical bytes removed | 3,866,268,828 bytes (3.60 GiB) |
| Observed increase in free space on `C:` | 3,991,465,984 bytes (3.72 GiB) |
| Approved material still locked/inaccessible | 1,768,039,458 bytes (1.65 GiB) |

The original 6.95 GB estimate included 1,326,900,893 bytes behind the `apps/mobile_authenticator_flutter/build` junction. That junction targeted `D:\GradleCache\xai-mobile-build`, outside the approved project root. The project-side junction was removed safely, but its external target and data were preserved.

## Categories removed

### Dependency environments and installs

- Removed `services/api_fastapi/.venv` and `engines/XAI-Compress/.venv`.
- Removed root `node_modules` and Angular `apps/web_angular/node_modules`.
- Root `.venv` and Next.js `apps/public_nextjs/node_modules` were reduced but could not be fully removed because running Python/Node processes hold native binaries open.

### Framework and compiler output

- Removed both Flutter `.dart_tool` trees.
- Removed Next.js `.next` and Angular `.angular`.
- Removed Rust `rust-core/target`.
- Removed the engine `build` tree and .NET `obj` tree.
- Removed the mobile Flutter project-side `build` junction without touching its external target.
- Desktop Flutter `build` and .NET `bin` were reduced but remain partially locked.

### Caches and disposable tests

- Removed root and engine pytest caches.
- Removed discovered source-tree `__pycache__` directories in the engine, API, analytics, scripts, and tools scopes.
- Removed unlocked disposable scratch pytest/integration basetemps.
- `engines/XAI-Compress/.test-tmp` and five scratch basetemps remain inaccessible and were not force-modified.

### Verified generated/temporary tracked files

- Removed six tracked, generated `engines/XAI-Compress/xai_compress.egg-info` files.
- Removed the stale tracked Word lock file `~$apport.docx` after confirming Microsoft Word was not running.
- Intentional empty package files and source placeholders were retained.

## Remaining locked generated paths

| Path | Remaining size | Reason |
| --- | ---: | --- |
| Root `.venv` | 1,110,590,762 bytes | Python PID 6204 holds `pydevd_cython` native module |
| `apps/public_nextjs/node_modules` | 388,345,181 bytes | Node PIDs 19524 and 20592 hold Next SWC native module |
| `apps/desktop_flutter/build` | 250,609,644 bytes | Windows denied removal of a generated Material Icons font |
| `engines/XAI-Compress/.test-tmp` | 15,967,906 bytes | Restricted/broken historical basetemp entries |
| `apps/admin_dotnet/bin` | 2,518,950 bytes | AdminDotNet PID 18976 holds the application DLL |
| Five `scratch/*pytest*` basetemps | 7,015 bytes | Restrictive ACL/reparse history; no permissions were changed |

These remain `GENERATED_RECREATABLE`, but process termination or ACL repair was outside this cleanup's safe execution boundary.

## Security result for `.env.example`

- The pgAdmin template value was non-placeholder and exactly matched the ignored runtime `.env` value.
- It was replaced without printing it with `REPLACE_WITH_RANDOM_PGADMIN_PASSWORD`.
- The previously empty PostgreSQL password entry was made explicit as `REPLACE_WITH_RANDOM_POSTGRES_PASSWORD`.
- All five sensitive template keys now contain obvious placeholders.
- The real ignored `.env` and `.env.admin.local` files were not modified; their timestamps remain unchanged.
- The exposed value was not found in the current Git index or any committed `.env.example` history.
- Credential rotation is still recommended because a real value existed in a tracked-path working file and may have been copied or shared outside Git.

## Lightweight validation

| Check | Result |
| --- | --- |
| `docker compose config --quiet` | PASS |
| PostgreSQL readiness | PASS — accepting connections; Compose reports healthy |
| PostgreSQL users | PASS — 7 after approved validation-account cleanup |
| PostgreSQL public tables | PASS — 13 |
| USER1 `m.taieb2k@gmail.com` | PASS — present, user, ACTIVE |
| USER2 `mohamed.taieb1@outlook.com` | PASS — present, user, ACTIVE |
| PFE Admin `pfe-admin@example.com` | PASS — present, admin, ACTIVE |
| Database cleanup | PASS — exactly 9 approved validation accounts removed in one committed transaction |
| Release manifest artifacts | PASS — 4/4 exist and sizes match; all remain `signed=false` |
| Screenshot evidence | PASS — 72 files; `report_ready` contains 16 files |
| Reports | PASS — directory retained |
| Final report evidence | PASS — retained |
| `.tmp`, `.xai-runtime`, `xai_platform.db` | PASS — all retained |
| Scientific data | PASS — data directory retained with 14,252 files |
| Checkpoints/models | PASS — checkpoint directory retained with 51 files |
| Required Hybrid V3 benchmark CSV, manifest, summary | PASS — all retained |
| Selector V2 checkpoint metadata | PASS — retained |

No build, benchmark, or test campaign was run.

## DATABASE CLEANUP

The database cleanup was executed after a second read-only schema and storage audit. No application user-deletion endpoint or supported maintenance command exists, so one asserted PostgreSQL transaction was used. The five exact owner-scoped storage directories were first moved atomically to a quarantine inside `xai_xai-storage`; the quarantine was purged only after `COMMIT`.

### Deleted validation accounts

| ID | Email | Classification |
| ---: | --- | --- |
| 1 | `e2e-f8e81f464e80@example.com` | Generated E2E account |
| 2 | `e2e-c05457fde767@example.com` | Generated E2E account |
| 3 | `mobile-e2e-33358d92@example.com` | Generated mobile E2E account |
| 4 | `e2e-2ae8b69b14bd@example.com` | Generated pipeline E2E account |
| 5 | `e2e-other-cbe63243b2e2@example.com` | Generated secondary E2E account |
| 6 | `mobile-e2e-f047998c@example.com` | Generated authenticated-mobile E2E account |
| 7 | `runtime-76bfc2c811c5f5ff@example.com` | Generated runtime-validation account |
| 8 | `runtime-901d3e19b78fa23d@example.com` | Generated runtime-validation account |
| 9 | `security-af86d63a5036823d@example.com` | Generated security-validation account |

### Deleted dependent rows

| Table/reference | Rows deleted |
| --- | ---: |
| `refresh_tokens.user_id` | 13 |
| `files.owner_id` | 5 |
| `audit_events.user_id` (unconstrained reference) | 22 |
| `share_codes.sender_id` | 0 |
| `share_codes.file_id` | 0 |
| `auth_events.user_id` | 0 |
| `auth_challenges.user_id` | 0 |
| `account_verification_challenges.user_id` | 0 |
| `authenticator_devices.user_id` | 0 |
| `totp_enrollments.user_id` | 0 |
| `recovery_codes.user_id` | 0 |
| `users` | 9 |

All other real-schema references were checked. No candidate device references, file-share references, protected-user references, or ambiguous/shared storage paths existed.

### Deleted exclusive storage artifacts

Ten files totaling 4,439,600 bytes were deleted from five exclusively owned directories:

- `/data/4/eab633909b776ed56742ceda/{source.bin,artifact.xaic}`
- `/data/6/53f46c02ed5ac751de0f7444/{source.bin,artifact.xaic}`
- `/data/7/9e487fce44c8254ea002756b/{source.bin,artifact.xaic}`
- `/data/8/bf57fb6353e1ed6adfd3c492/{source.bin,artifact.xaic}`
- `/data/9/ab0609f96f2c37586284c84e/{source.bin,artifact.xaic}`

Each directory had zero references from non-candidate file rows and zero share-code references. The original directories and temporary quarantine are absent after commit. The `xai_xai-storage` and `xai_db-data` volumes were preserved.

### Transaction and preservation verification

| Check | Result |
| --- | --- |
| Transaction | COMMITTED |
| Users before / after | 16 / 7 |
| Exact candidate IDs/emails remaining | 0 / 0 |
| Public tables | 13 |
| USER1 | `m.taieb2k@gmail.com`, user, ACTIVE; 4 files, 3 shares preserved |
| USER2 | `mohamed.taieb1@outlook.com`, user, ACTIVE; existing state preserved |
| PFE Admin | `pfe-admin@example.com`, admin, ACTIVE |
| Intentional demo accounts | 4 preserved |
| Genuine files / shares remaining | 5 / 4 |
| Non-validation audit events remaining | 49 |
| FK and unconstrained user-reference orphans | 0 across every checked relationship |
| Migrations | Versions `000`–`005`, checksums, and applied timestamps unchanged |
| PostgreSQL health | Accepting connections; Compose healthy |

No scientific, benchmark, report, release, USER1/USER2, admin, or shared demo evidence was removed.

## Remaining REVIEW_REQUIRED items

- `.tmp` mixed tracked/temp/evidence content.
- `.xai-runtime` accepted-run logs mixed with generated output.
- Root `xai_platform.db` and any other SQLite database.
- Tracked .NET publish artifacts and nested duplicates.
- Engine `.kaggle_*` snapshots and historical tracked result trees.
- Root package manifests, older report workflow, and other legacy candidates from `CLEANUP_AUDIT.md`.
- The ten locked/inaccessible generated roots listed above.
- External `D:\GradleCache\xai-mobile-build`; its junction was removed, but the target was not approved for deletion.

## Git status summary

| Category | Count |
| --- | ---: |
| Tracked modifications | 0 |
| Tracked deletions | 1,086 |
| Untracked files | 2,191 |
| Cleanup-caused tracked deletions | 7 |
| Tracked deletions predating cleanup | 1,079 |

The seven cleanup-caused tracked deletions were reviewed against repository/build configuration rather than filename alone:

| Deleted path | Finding | Recommended disposition |
| --- | --- | --- |
| `engines/XAI-Compress/xai_compress.egg-info/PKG-INFO` | Generated by the configured `setuptools.build_meta` backend, but the scientific corpus/results reference the tracked `egg-info` paths and hashes | RESTORE_RECOMMENDED for reproducibility; not restored in this task |
| `engines/XAI-Compress/xai_compress.egg-info/SOURCES.txt` | Same generated packaging tree and scientific-reference issue | RESTORE_RECOMMENDED; not restored |
| `engines/XAI-Compress/xai_compress.egg-info/dependency_links.txt` | Referenced by corpus manifests and Hybrid V2 selector data | RESTORE_RECOMMENDED; not restored |
| `engines/XAI-Compress/xai_compress.egg-info/entry_points.txt` | Referenced by corpus manifests and Hybrid V2 selector data | RESTORE_RECOMMENDED; not restored |
| `engines/XAI-Compress/xai_compress.egg-info/requires.txt` | Generated metadata within the scientifically referenced tracked tree | RESTORE_RECOMMENDED; not restored |
| `engines/XAI-Compress/xai_compress.egg-info/top_level.txt` | Generated metadata within the scientifically referenced tracked tree | RESTORE_RECOMMENDED; not restored |
| `~$apport.docx` | Microsoft Word lock file; not created or consumed by `generate_report.py`, and no product/build dependency exists | REMAIN_DELETED |

The scientific references occur in `data/hybrid_selector/corpus_manifest.csv`, Hybrid V2 corpus/selector datasets, and retained model-search/Kaggle provenance. Consequently, the six `egg-info` deletions remain `REVIEW_REQUIRED` despite being technically regenerable. Per instruction, no deletion was restored and no pre-existing deletion was changed.

`.env.example` remains clean relative to the Git index. `reports/CLEANUP_AUDIT.md` is tracked and this cleanup report is untracked. No commit or push was performed.
