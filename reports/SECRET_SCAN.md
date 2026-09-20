# Sanitized secret scan

No secret values are reproduced in this report.

| PATH / LOCATION | SECRET TYPE | TRACKED? | ACTION |
| --- | --- | --- | --- |
| `.env` | Local database/app/demo credentials and tokens | NO (ignored) | Keep untracked; rotate if reused outside local development. |
| `.env.admin-test` | Local test credentials | NO | Keep untracked and local only. |
| `.env.render.production` | Production-shaped database/app/email configuration | NO | Keep untracked; rotation required for any value that was ever deployed or shared. |
| `.env.example` | Sensitive field names with placeholder-only values | NO (currently untracked) | Add/review deliberately; keep placeholders only. |
| `docker-compose.yml`, `compose.devtest.yml` | Development fallback credential-like literals and environment references | YES | Never reuse development defaults in production; production must supply secrets externally. |
| `deployment/.env.render.api.example` | Placeholder/reference configuration | YES | Keep placeholder-only; review before deployment. |
| `services/api_fastapi/tests/**`, `scripts/test_*.py` | Synthetic test tokens/TOTP/credential fixtures | YES | Keep demonstrably synthetic; never copy into deployed configuration. |

The scan found no tracked private signing-key block. Broad identifier matches in application code (for example, variable names such as access token) were not treated as leaked values. Historical production-shaped local configuration cannot be proven unused; any real credential formerly placed there requires rotation.
