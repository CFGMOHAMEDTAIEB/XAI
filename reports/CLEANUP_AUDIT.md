# Repository Cleanup Audit

Prepared: 2026-09-26. This is an audit and proposal only. No file, directory, database row, storage object, Docker volume, release artifact, checkpoint, or evidence item was deleted or moved.

## Summary

The inventory covered the working tree at `C:\Users\ss\Desktop\XAI\XAI`, excluding Git's internal `.git` object store and without following directory reparse points. The repository was already heavily dirty before this audit, so tracked changes and existing deletions must not be normalized as part of cleanup.

| Measure | Observed |
| --- | ---: |
| Files | 166,579 |
| Directories discovered | 19,965 |
| Logical size | 78,911,955,162 bytes (78.91 GB / 73.49 GiB) |
| Inaccessible/stale directories reported | 23 |
| Directory reparse points found in bounded scan | 953 |
| Pre-report Git status entries | 3,330 |
| Pre-existing deleted / modified / untracked entries | 1,079 / 8 / 2,243 |

Most space is intentional scientific data: `engines/XAI-Compress/data` is 66.34 GiB and is protected. The conservative generated/recreatable candidate set is approximately 6.95 GB (6.47 GiB), predominantly Flutter builds, virtual environments, dependency installs, Rust targets, and Next.js output.

### Root-level files

| Path | Classification | Recommendation |
| --- | --- | --- |
| `.dockerignore`, `.gitignore` | Active configuration | KEEP |
| `.env` | Ignored local runtime secrets | KEEP_LOCAL; never commit or print |
| `.env.admin.local` | Ignored dedicated admin credentials | KEEP_LOCAL; required for the protected admin account |
| `.env.admin-test` | Ignored isolated-test credentials; referenced by three scripts and `compose.devtest.yml` | KEEP_LOCAL unless that workflow is explicitly retired |
| `.env.render.production` | Ignored production-shaped local configuration; referenced by `scratch/check_production_auth_schema.py` | REVIEW_REQUIRED; retain securely and rotate any value ever shared/deployed |
| `.env.example` | Tracked template | KEEP, but security review is required because `PGADMIN_DEFAULT_PASSWORD` is not placeholder-like |
| `.errorviz-version` | Tracked and referenced by corpus/benchmark manifests | KEEP |
| `~$apport.docx` | 162-byte tracked Word lock file | SAFE_TO_DELETE only after Word is closed and explicit approval is given for a tracked deletion |
| `compose.devtest.yml`, `docker-compose.yml` | Active runtime/test orchestration | KEEP |
| `generate_report.py`, `rapport.docx` | Tracked report generator and generated PFE document | KEEP; review only if the older report workflow is formally retired |
| `package.json`, `package-lock.json` | Root package manifests containing only `@xyflow/react` | REVIEW_REQUIRED; no non-generated source import was found, but do not remove without confirming the earlier ErrorViz workflow is retired |
| `README.md` | Project documentation | KEEP |
| `sample.txt` | Tracked 26-byte sample/corpus input | KEEP |
| `servers.json` | Active pgAdmin server registration mounted by Compose; contains no password | KEEP |
| `xai_platform.db` | Ignored 155,648-byte SQLite database with schema and zero users | REVIEW_REQUIRED; the FastAPI default still names `sqlite:///./xai_platform.db`, so it is not safe to delete blindly |

### Root-level directories

| Path(s) | Classification | Recommendation |
| --- | --- | --- |
| `.git`, `.github`, `.vscode` | Repository/automation/editor configuration | KEEP |
| `analytics`, `apps`, `deployment`, `docs`, `engines`, `infrastructure`, `notebooks`, `scripts`, `services`, `tools` | Active source, configuration, research, or documentation | KEEP |
| `FINAL_REPORT`, `rapport-pfe`, `reports` | PFE deliverables and validation evidence | KEEP |
| `releases` | Manifested download artifacts | KEEP; all four remain truthfully unsigned/test-only |
| `dist` | Built/E2E evidence, not ordinary disposable output in this repository | KEEP |
| `scratch` | Mixed validation evidence and test basetemps | REVIEW_REQUIRED path by path; preserve `production-*`, runtime/security evidence, and reports |
| `.tmp` | Mixed tracked dependencies/publish output plus ignored previews/test basetemps and untracked screenshots | REVIEW_REQUIRED path by path |
| `.xai-runtime` | Ignored runtime/test/build output with accepted-run logs | REVIEW_REQUIRED until raw evidence retention is confirmed |
| `.venv`, `node_modules`, `.pytest_cache` | Recreatable environment/dependencies/cache | SAFE_TO_DELETE after approval, with recreation cost noted |
| `labs`, `packages` | Small supplemental source/prototypes | KEEP unless a separate source-retirement review proves them obsolete |
| `storage` | Empty local runtime placeholder | KEEP; do not confuse it with the active `xai_xai-storage` Docker volume |

## Empty Files

The bounded scan found 161 zero-byte files outside protected data, release, dependency, and virtual-environment trees. Zero length alone is not proof of disposability.

| Category | Examples | Recommendation |
| --- | --- | --- |
| Semantic package files | `analytics/.../__init__.py`, `services/api_fastapi/app/__init__.py` | KEEP |
| Test fixtures | empty `input.bin`, `restored.bin`, `in`, `restored`, and `pyproject.toml` under `.xai-runtime`, `.test-tmp`, and historical pytest results | Delete only with their proven-recreatable parent basetemp; preserve tracked historical evidence |
| Build cache/lock markers | `.Up2Date`, static-web-asset caches, Rust locks/stderr, Flutter ephemeral locks | SAFE_TO_DELETE with the containing generated build directory |
| Empty logs | `.tmp/*err.log`, `.xai-runtime/flutter-desktop.err.log`, engine training/controller logs | REVIEW_REQUIRED where logs may be evidence; otherwise safe after evidence consolidation |
| Suspicious shell-created names | `apps/mobile_authenticator_flutter/cls`, `apps/mobile_authenticator_flutter/powershell` | REVIEW_REQUIRED; empty and likely accidental, but source-owner confirmation is required |

## Empty Directories

The bounded scan found 582 empty directories. Most are generated pytest basetemps, model-search test fixtures, .NET static-web-asset folders, Flutter/CMake configuration folders, and Gradle caches.

- `.tmp/pytest-api-*`: generated test basetemps; safe only as whole, verified untracked roots.
- `.xai-runtime/engine-pytest/*`: generated accepted-run test workspaces; retain until raw evidence policy is confirmed.
- Flutter `build`, `.dart_tool`, and Gradle/CMake empty folders: safe with their generated parent trees.
- Model-search fixtures inside protected `results` or checkpoint trees: do not remove individually.
- Twenty-three stale or inaccessible directories and 953 reparse points were observed. Never use a broad recursive delete across these paths without resolving each final target first.

## Temporary Files

| Path/pattern | Size/state | Classification | Recommendation |
| --- | ---: | --- | --- |
| `~$apport.docx` | 162 bytes, tracked | Stale Word lock candidate | Delete only after Word is closed and approval covers the tracked change |
| `.tmp/pdf_render/`, `.tmp/pdf_render_final/` | 6.13 MiB combined | Generated report previews | SAFE_TO_DELETE after confirming the final DOCX/PDF remains; many pages are exact duplicates |
| `.tmp/pytest-api-*` | about 6 KiB plus 150+ reparse entries | Generated test basetemps | SAFE_TO_DELETE only with reparse-target validation |
| `engines/XAI-Compress/.test-tmp` | 15.23 MiB | Untracked test basetemps | SAFE_TO_DELETE; do not touch protected `results`/checkpoints |
| `scratch/*pytest*`, `scratch/integration-final-tests-*` | small/mostly empty | Generated test basetemps | SAFE_TO_DELETE if accessible and untracked |
| `.tmp/admin-ui-publish` | 1.25 MiB, 61 tracked files | Publish output/evidence | REVIEW_REQUIRED; tracked and duplicated elsewhere |
| `.tmp/*.png` current desktop/mobile captures | six untracked files | Visual evidence | KEEP |
| `.xai-runtime` | 34.80 MiB | Runtime logs and generated test/build output | REVIEW_REQUIRED; do not remove accepted-run logs blindly |

## Generated/Recreatable

These paths are candidates, not approved deletions. Sizes are logical sizes measured without following junctions.

| Path | Size | Classification | Recreation impact |
| --- | ---: | --- | --- |
| `apps/mobile_authenticator_flutter/build` | 1,265.43 MiB | SAFE_TO_DELETE | Flutter/Gradle rebuild required |
| Root `.venv` | 1,216.72 MiB | SAFE_TO_DELETE | Python environment reinstall required |
| `apps/desktop_flutter/build` | 694.61 MiB | SAFE_TO_DELETE | Flutter/Visual Studio rebuild required |
| `engines/XAI-Compress/.venv` | 640.00 MiB | SAFE_TO_DELETE | Engine environment reinstall required |
| `apps/desktop_flutter/.dart_tool` | 614.44 MiB | SAFE_TO_DELETE | `flutter pub get` and native regeneration required |
| `apps/mobile_authenticator_flutter/.dart_tool` | 607.25 MiB | SAFE_TO_DELETE | `flutter pub get` and native regeneration required |
| `engines/XAI-Compress/rust-core/target` | 396.91 MiB | SAFE_TO_DELETE | Cargo rebuild required |
| `apps/public_nextjs/node_modules` | 391.98 MiB | SAFE_TO_DELETE | Locked npm install required |
| `services/api_fastapi/.venv` | 339.49 MiB | SAFE_TO_DELETE | API environment reinstall required |
| `apps/web_angular/node_modules` | 274.76 MiB | SAFE_TO_DELETE | Locked npm install required |
| `apps/public_nextjs/.next` | 154.59 MiB | SAFE_TO_DELETE | Next.js rebuild required |
| Root `node_modules` | 10.88 MiB | SAFE_TO_DELETE if root package is retained | npm install required |
| `apps/web_angular/.angular` | 9.81 MiB | SAFE_TO_DELETE | Angular cache rebuild required |
| `.tmp` untracked previews/test roots | up to 7.98 MiB, mixed with tracked material | REVIEW_REQUIRED | Delete only enumerated untracked subpaths |
| `apps/admin_dotnet/bin`, `apps/admin_dotnet/obj` | 2.99 MiB | SAFE_TO_DELETE | .NET rebuild required |
| Pytest/bytecode/egg-info caches outside environments | under 2 MiB observed, excluding test basetemps | SAFE_TO_DELETE when untracked | Regenerated automatically |

`apps/web_angular/dist` was not present. `apps/admin_dotnet/artifacts` is generated but has 81 tracked files and is therefore excluded from automatic cleanup. Protected releases, checkpoint files, benchmark outputs, and scientific data are also excluded regardless of whether they could technically be regenerated.

## Duplicate Files

A targeted SHA-256 scan of 885 cleanup-candidate/publish/test files found 139 exact-duplicate groups and 21,272,578 duplicate bytes. This is not an exhaustive repository-wide deduplication scan and its recoverable bytes overlap the generated-directory estimate above.

| Paths | SHA-256 | Observation / recommendation |
| --- | --- | --- |
| Seven `engines/XAI-Compress/.test-tmp/*/test_large_file_hybrid_streami0/large.bin` files | `376086d7d3eab886ce69d200a9c68ae94af5d7c5f78931a70ce1fd9d29c95761` | 2,000,000 bytes each; delete with `.test-tmp` after approval |
| Six copies of `Microsoft.IdentityModel.Tokens.dll` across `.tmp/admin-ui-publish`, `.xai-runtime`, and three `apps/admin_dotnet/artifacts/ui-publish*` trees | `479dbbe8b91eb993bfb63e3a37bb7c8f11a6e0189823871123b89fb3d4f9b54f` | Remove only ignored runtime/temp copies; tracked artifact trees require release/evidence review |
| Twenty-nine nested `AdminDotNet.deps.json` copies across the same publish trees | `3284b82800f56372b8f940175b07c26779b0fc8ff21e31e46fa354a68cedf3a0` | Indicates recursively nested publish output; REVIEW_REQUIRED because 81 artifact files are tracked |
| `docs/screenshots/10_decompression/10_user1_user2_sha256_verification.png` and `docs/screenshots/report_ready/fig_user1_user2_sha256.png` | `92ac0f425c8cd7c060d5f7d2a3a30dc1b376a52db32ee23fdf7a25648da7ffd9` | Exact evidence duplicate; KEEP both while source/report references use both layouts |
| `docs/screenshots/09_recipient/09_user2_registration.png` and `docs/screenshots/report_ready/fig_user2_registration.png` | `0f9c1338887835df804a33a229df9923cbed369449fa15d9bccc06eaea7f2f41` | Exact evidence duplicate; KEEP both while referenced |
| `.tmp/pdf_render/page-007.png` and `.tmp/pdf_render_final/page-007.png` | `86cfc28f92f99dfc9741ff4baf7a6a15b0a2329d441d5539ed3f2ac46a0eed35` | Disposable previews after final-document verification |

The evidence-image scan covered 222 images and found 86 duplicate groups. Evidence duplicates are not cleanup candidates solely because their bytes match; many intentionally provide both chronological and report-ready layouts.

## Legacy Candidates

| Path | Current references | Recommendation |
| --- | --- | --- |
| Root `xai_platform.db` | FastAPI's default URL still resolves to a cwd-relative file; database has schema and zero users | REVIEW_REQUIRED; retain until every local launcher supplies PostgreSQL explicitly or the SQLite fallback is retired |
| Root `package.json`, `package-lock.json`, `node_modules` | Only `@xyflow/react`; no non-generated import found | REVIEW_REQUIRED for manifests; root `node_modules` is safe to recreate/remove after approval |
| `generate_report.py`, `rapport.docx` | Generator explicitly writes this DOCX; newer `FINAL_REPORT` also exists | KEEP as historical PFE source/output unless document owner retires it |
| `labs`, `packages`, placeholder supplemental services | Not part of the primary Compose runtime | KEEP; inactive source is not disposable generated content |
| Engine `.kaggle_*` snapshots | Approximately 0.48 GiB across downloaded/source/output snapshots; linked to training/recovery history | REVIEW_REQUIRED; scientific provenance takes precedence over space recovery |
| `engines/XAI-Compress/results/pytest-*` and `results/hybrid_v3/tmp` | Historical tests; 456 files in `hybrid_v3/tmp` are tracked and current deletions predate this audit | KEEP / REVIEW_REQUIRED; never bulk-delete |
| `.env.render.production` | Referenced by a production-schema check script and flagged in `SECRET_SCAN.md` | Securely retain pending explicit retirement/rotation decision |

## Database Test Accounts

PostgreSQL was inspected read-only in the existing `xai_db-data` volume. There are 16 users. No deletion endpoint or supported user-maintenance command was found; `/admin/users` is read-only. All nine foreign keys to `users` are non-cascading, so direct deletion without an explicit plan would fail or orphan filesystem artifacts.

### Verified validation candidates

The naming patterns are generated by repository scripts (`scripts/test_local_pipeline.py`, `scripts/test_security_pipeline.py`, and the mobile/runtime validation tooling). These nine accounts are `SAFE_TO_DELETE` only as a separately approved database operation.

| ID | Email | Files | Refresh tokens | Other FK dependencies | Recommendation |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | `e2e-f8e81f464e80@example.com` | 0 | 1 | 0 | Candidate |
| 2 | `e2e-c05457fde767@example.com` | 0 | 1 | 0 | Candidate |
| 3 | `mobile-e2e-33358d92@example.com` | 0 | 1 | 0 | Candidate |
| 4 | `e2e-2ae8b69b14bd@example.com` | 1 | 1 | 0 | Candidate; includes source/artifact pair |
| 5 | `e2e-other-cbe63243b2e2@example.com` | 0 | 1 | 0 | Candidate |
| 6 | `mobile-e2e-f047998c@example.com` | 1 | 2 | 0 | Candidate; includes source/artifact pair |
| 7 | `runtime-76bfc2c811c5f5ff@example.com` | 1 | 2 | 0 | Candidate; includes source/artifact pair |
| 8 | `runtime-901d3e19b78fa23d@example.com` | 1 | 2 | 0 | Candidate; includes source/artifact pair |
| 9 | `security-af86d63a5036823d@example.com` | 1 | 2 | 0 | Candidate; includes source/artifact pair |

The five file rows reference ten objects in five owner-scoped directories under `/data/4`, `/data/6`, `/data/7`, `/data/8`, and `/data/9`. Their recorded logical payload is approximately 4.23 MiB. No share codes, TOTP enrollments, authenticator devices, auth challenges/events, recovery codes, or verification challenges depend on these candidates.

### Protected and intentional accounts

| ID(s) | Account(s) | Classification | Recommendation |
| ---: | --- | --- | --- |
| 10-13 | `web-demo@xai.local`, `desktop-demo@xai.local`, `web-demo@example.com`, `desktop-demo@example.com` | Intentional local demo accounts; two have file/share/token state | KEEP unless the demo workflow is explicitly retired |
| 14 | `m.taieb2k@gmail.com` | Protected real user with files, shares, tokens, and verification challenges | MUST_PRESERVE |
| 15 | `mohamed.taieb1@outlook.com` | Protected real user with token and verification state | MUST_PRESERVE |
| 16 | `pfe-admin@example.com` | Protected dedicated admin | MUST_PRESERVE |

### Proposed safe database cleanup mechanism

1. Require separate explicit approval for the exact nine IDs/emails above; do not select accounts by domain alone.
2. Re-run the dependency query and abort if IDs, emails, roles, counts, or protected-account state differ.
3. Because the application has no deletion mechanism, use a reviewed one-off maintenance transaction rather than an ad-hoc console command.
4. Before the transaction, move only the five owner-scoped storage directories to a dated quarantine path inside `xai_xai-storage`; do not delete the volume. This makes artifact rollback possible.
5. In one PostgreSQL transaction, lock the nine rows, verify exact predicates and expected counts, delete their 13 refresh-token rows and five file rows, verify that all other child tables remain at zero, then delete exactly nine user rows. Roll back on any mismatch.
6. Verify USER1, USER2, ADMIN, all demo accounts, and their dependency counts after commit. Restore quarantined artifacts if verification fails.
7. Retain the quarantine until a later explicit irreversible-deletion approval. No database or storage action was taken during this audit.

## Must Preserve

- `xai_db-data` and the existing PostgreSQL schema/migrations.
- `xai_xai-storage` except for a separately approved, recoverable operation on the exact five validation-owned directories.
- USER1 `m.taieb2k@gmail.com`, USER2 `mohamed.taieb1@outlook.com`, and ADMIN `pfe-admin@example.com`.
- Intentional demo users unless their workflow is explicitly retired.
- `engines/XAI-Compress/data`, checkpoints, models, corpus manifests, benchmark CSV/JSON, and scientific results/provenance.
- `releases/manifest.json` and all four release artifacts.
- `reports`, `FINAL_REPORT`, `rapport-pfe`, `docs/screenshots`, report-ready figures, visual evidence, test evidence, and accepted-run logs pending retention review.
- Source code, migrations, fixtures, configuration, documentation, active pgAdmin `servers.json`, and existing unrelated worktree changes.
- Docker volumes `xai_clamav-data`, `xai_pgadmin-data`, and persistent application volumes. Isolated `xai_devtest-*` volumes require separate review rather than automatic pruning.

## Review Required

1. The worktree has 1,079 pre-existing tracked deletions and 2,243 untracked entries; cleanup must never use `git clean`, reset, or broad path deletion.
2. `.env.example` contains a non-placeholder-like pgAdmin password value. Replace it with a clear placeholder and rotate it if it was ever used; do not expose the current value.
3. `.tmp` contains 318 tracked files, including dependency and publish trees. Only individually proven untracked preview/basetemp paths are candidates.
4. `apps/admin_dotnet/artifacts` contains 81 tracked publish files and nested duplicates; release/evidence references must be resolved before consolidation.
5. `.xai-runtime` contains accepted-run logs alongside generated output; raw-evidence retention must be decided first.
6. Root `xai_platform.db`, root package manifests, the older DOCX workflow, and engine Kaggle snapshots need owner/provenance decisions.
7. The 23 inaccessible/stale directories and 953 reparse points require literal-path and resolved-target verification before any recursive operation.
8. The nine database candidates require the separate high-risk plan above because no intended application deletion mechanism exists and filesystem objects accompany five rows.
9. The tracked Word lock file and empty `cls`/`powershell` files look accidental but still require explicit tracked/source-owner approval.

## Potential disk space recoverable

| Scope | Potential recovery | Confidence |
| --- | ---: | --- |
| Clearly recreatable environments, dependency installs, build output, Rust target, framework caches, and untracked test basetemps listed above | approximately 6.95 GB (6.47 GiB) | High data-safety confidence; potentially expensive to rebuild |
| `.xai-runtime` | up to 34.80 MiB | Medium; accepted-run logs may need preservation |
| Mixed `.tmp` content | up to 7.98 MiB | Low as a whole; 318 files are tracked and six current screenshots are evidence |
| Exact duplicates in targeted candidate scan | 20.29 MiB | High byte identity, but overlaps the generated estimate and includes tracked evidence |
| Nine validation accounts' recorded file payloads | approximately 4.23 MiB plus small row/token overhead | High candidate identity; high operational risk without approved transaction/quarantine |

Protected scientific data (66.34 GiB), release artifacts, checkpoints, reports, screenshots, and evidence are deliberately excluded from recoverable-space totals.
