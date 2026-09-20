# XAI-Compress test report

Generated: 2026-09-20 (final validation campaign)

## A. Current reproducible campaign

| COMPONENT | COMMAND | COLLECTED | PASSED | FAILED | SKIPPED | BLOCKED | DURATION | NOTES |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| FastAPI | `docker run ... xai-backend python -m pytest tests -q` | 166 | 166 | 0 | 0 | 0 | 29.75 s | Current Docker test log; 870 warnings. |
| XAI-Compress Python engine | `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp <fresh OS temp>` | 210 | 206 | 0 | 4 | 0 | 94.96 s | Clean standalone run. |
| Rust core | `cargo test --manifest-path engines/XAI-Compress/rust-core/Cargo.toml` | 2 | 2 | 0 | 0 | 0 | 9.16 s build; tests 0.00 s | Warnings do not change the passing result. |
| Angular | `npm.cmd test` | 24 | 24 | 0 | 0 | 0 | 85.28 s | Vitest current log. |
| Next.js unit | `node --test tests/*.test.mjs` | 8 | 8 | 0 | 0 | 0 | 0.495 s | Node test runner current log. |
| Next.js quality/build | `npm run lint`, `npm run typecheck`, `npm run build` | build checks | N/A | 0 | 0 | 0 | Not reported | Build success is not counted as runtime-test pass. |
| Flutter Desktop | `flutter test` | 39 | 37 | 0 | 2 | 0 | about 15 s | Two controlled live tests skipped by explicit environment gates. |
| Flutter Mobile | `flutter test` | 22 | 22 | 0 | 0 | 0 | about 15 s | Current Flutter log. |
| .NET Admin | `dotnet run --project tools/admin_integration_tests/AdminIntegrationTests.csproj` | 2 scenarios | 2 | 0 | 0 | 0 | Not reported | Client-error and login/MFA/role/logout scenarios passed. NuGet advisory retrieval warned separately. |

The earlier 88 engine setup errors were caused by a stale Windows ACL basetemp directory. A clean standalone execution using a fresh OS temporary directory completed with 206 passed and 4 skipped.

## B. Historical or superseded evidence

- The earlier engine result with 88 setup errors is superseded by the clean run above and is not an engine assertion failure.
- A later engine output stream stopped at 34%. It is incomplete and is not counted.
- The pre-clean report row showing 118 passed, 1 failed, and 4 skipped is superseded and is not merged into this campaign.

## C. Blocked or not executed

- No component test command in the current table is classified as blocked.
- Flutter Desktop's two skips are skips, not passes or blockers.
- Physical Android-device behavior, signed installer behavior, and production deployment integration were not tested by this host campaign.

Interpretation rules: **BuildPass != RuntimePass**, **HistoricalPass != CurrentPass**, **MockPass != RealIntegrationPass**, **Blocked != Failed**, and **Blocked != Passed**.
