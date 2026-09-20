# Repository cleanup plan

Prepared: 2026-09-20. The worktree was already dirty before this plan. Cleanup must not revert tracked changes or remove research/release evidence.

| PATH | REASON | ACTION | RISK |
| --- | --- | --- | --- |
| `.pytest_cache/` | Untracked pytest cache; inaccessible entries may exist | REMOVE_SAFE if accessible | LOW |
| `services/api_fastapi/.pytest_cache/`, `engines/.pytest_cache/` | Untracked pytest metadata | REMOVE_SAFE if accessible | LOW |
| `**/__pycache__/`, `*.pyc` | Re-creatable interpreter bytecode | REMOVE_SAFE when untracked | LOW |
| `node_modules/` and app-local `node_modules/` | Re-creatable dependency installs | KEEP for this run; ignore | LOW data risk, HIGH time/network cost to recreate |
| `services/api_fastapi/.venv/`, root `.venv/` | Re-creatable virtual environments | KEEP for this run; ignore | LOW data risk, HIGH time/network cost to recreate |
| `apps/web_angular/dist/`, `apps/public_nextjs/.next/` | Generated web builds | REMOVE_SAFE only when untracked and not in use | LOW |
| Flutter `build/`, `.dart_tool/` | Generated Flutter intermediates; build may be a junction to an external drive | KEEP; ignore | MEDIUM because artifact evidence/junction targets exist |
| `.tmp/*.log`, `.tmp/pdf_render*/` | Generated process logs and rendered PDF pages | REMOVE_SAFE only when untracked; tracked `.tmp` files stay | LOW |
| `.tmp/pytest-*` | Generated test basetemps | REMOVE_SAFE only when untracked and accessible | LOW; ACL/junction anomalies present |
| `scratch/*pytest*/`, `scratch/integration-final-tests-*` | Generated test basetemps already ignored | REMOVE_SAFE only when untracked and accessible | LOW; some inaccessible paths present |
| `engines/XAI-Compress/results/hybrid_v3/tmp/` | Test temporary output, but 456 files are tracked and current deletions predate this task | REVIEW_REQUIRED; no automatic removal | HIGH: overlaps existing tracked changes |
| `engines/XAI-Compress/results/pytest-*` | Historical test evidence, some tracked | REVIEW_REQUIRED; keep | HIGH: may support reproducibility |
| `apps/admin_dotnet/bin/`, `obj/` | Generated build intermediates | REMOVE_SAFE when untracked and not in use | LOW |
| `apps/admin_dotnet/artifacts/ui-publish*` | Repeated nested publish output; 81 files tracked | REVIEW_REQUIRED; keep | HIGH: may be referenced release evidence |
| `engines/XAI-Compress/results/model_search/imports/` | Large source/checkpoint imports | REVIEW_REQUIRED; keep | HIGH: experiment provenance |
| `engines/XAI-Compress/checkpoints/`, dataset manifests, benchmark CSV/JSON | Scientific reproducibility inputs/evidence | KEEP | HIGH |
| `FINAL_REPORT/`, `rapport-pfe/`, `docs/product-truth-audit/`, `scratch/production-*` | Graduation/audit evidence | KEEP | HIGH |
| `services/api_fastapi/xai_platform.db` | Local database with possible user state | REVIEW_REQUIRED; never auto-delete | HIGH |
| `dist/production-artifacts/`, APK/Windows ZIPs | Existing test/release evidence | KEEP until manifest/release review | HIGH |

## Automatic cleanup boundary

Only untracked cache/build paths proven re-creatable will be removed. No tracked file, database, checkpoint, benchmark result, release artifact, source file, migration, fixture, or evidence report will be deleted. Paths with access-control errors or directory links will be retained rather than force-removed.

## Ignore updates

The existing ignore file already covers virtual environments, Python caches, dependencies, generic `build`, `bin`, `obj`, `dist`, local databases, XAIC files, and integration basetemps. It should additionally ignore Next.js `.next` output, root pytest caches explicitly, transient `.tmp` logs/rendered pages, local runtime state, and notebook checkpoints while leaving tracked evidence unaffected.
