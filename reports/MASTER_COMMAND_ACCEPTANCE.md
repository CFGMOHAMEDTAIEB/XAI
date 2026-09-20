# Master command acceptance

`scripts/xai.ps1` has validated dispatch entries for all required commands. Expensive commands were not rerun after authoritative current evidence existed.

| COMMAND | STATUS | CURRENT EVIDENCE / LIMITATION |
| --- | --- | --- |
| `start` | BLOCKED | Earlier current campaign started successfully; final cold-start attempt is blocked because Docker Desktop's Linux engine is unavailable. |
| `status` | BLOCKED | Dispatch exists; final Docker CLI inspection is blocked by the unavailable engine. |
| `health` | PASS | Earlier current campaign passed all seven HTTP checks. Final post-stop endpoints are offline. |
| `seed` | PASS | Current campaign verified idempotent two-user seeding. |
| `test` | PASS | Current component logs are summarized in `TEST_REPORT.md`. |
| `benchmark` | PASS | Authoritative 560-row report regenerated/validated. |
| `notebook` | PASS | Current clean-kernel command evidence and structural QA passed. |
| `build` | PASS | Current release artifacts exist; Flutter Windows fresh build evidence is retained. |
| `release` | PASS | Four manifest-listed artifacts match local size/SHA-256. |
| `demo` | PASS | Current real two-user API E2E report is PASS. |
| `clean` | NOT_TESTED | Dispatch exists. The full master clean command was not rerun after the Docker failure; only the exact temporary download directory created by this validation was removed. |
| `stop` | BLOCKED | Command was attempted and failed because the Docker engine pipe was already absent; persistent volumes were not removed. |

Build success is not runtime success. Dispatch presence is not execution success. Historical success is not substituted for a blocked final cold-start gate.
