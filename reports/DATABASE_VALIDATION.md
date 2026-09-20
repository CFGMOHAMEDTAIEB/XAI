# Database final validation

## Sanitized result

| CHECK | STATUS | EVIDENCE / LIMITATION |
| --- | --- | --- |
| PostgreSQL health | PASS | Current campaign had a healthy persistent PostgreSQL service and successful application authentication before the host Docker engine stopped. |
| Migrations current | PASS | Current campaign applied and checked migrations without resetting or recreating the database. |
| Schema drift | PASS | Existing schema checker evidence reports migration/model alignment, constraints, indexes, idempotence, and rollback checks as passing. |
| Demo USER A | PASS | Current two-user E2E authenticated USER A through the normal API. |
| Demo USER B | PASS | Current two-user E2E authenticated USER B through the normal API. |
| E2E persistence | PASS | The persisted file/share records were usable across owner download, recipient redemption, and authorization checks in the current E2E. |
| pgAdmin HTTP | PASS | Current campaign HTTP health suite reached `http://localhost:15052`. |
| Post-cold-start schema recheck | BLOCKED | Docker Desktop's Linux engine named pipe was absent after the stack stopped, so the final repeat of `check-db-schema.ps1` could not run. |

No volume was deleted, no database was reset, and no password, token, password hash, refresh token, or TOTP value is included here. PostgreSQL's configured host endpoint is `localhost:15432`.
