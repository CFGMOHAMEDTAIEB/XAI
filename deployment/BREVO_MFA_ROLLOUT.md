# Brevo MFA rollout

The authoritative audit is [XAI_PLATFORM_AUDIT_2026-09-09.md](../docs/XAI_PLATFORM_AUDIT_2026-09-09.md). The earlier MFA_FLOW.md describes the previous Resend-only validation and is historical.

1. Require passing backend, mobile, portal, public-site, desktop and admin checks before deploying. Do not treat a local build as a live-flow result.
2. In the backend environment configure `EMAIL_PROVIDER=brevo`, `BREVO_API_KEY` privately, `BREVO_SENDER_EMAIL=m.taieb2k@gmail.com`, `BREVO_SENDER_NAME=XAI Compress`. Keep the existing finite `SMTP_TIMEOUT_SECONDS` (30). The operator enters the key manually; never put it in client variables or source files.
3. With the normal backend database environment active, run from `services/api_fastapi`:

   ```sh
   python -c "from app.db import engine; from app.models import TotpEnrollment; TotpEnrollment.__table__.create(engine, checkfirst=True)"
   ```

   This is the additive table also defined in `migrations/001_totp_enrollments.sql`. Verify the table in PostgreSQL without selecting user secrets. Existing startup create_all can create missing tables but is not a versioned migration runner. No production migration was executed by this audit.
4. Keep production PostgreSQL, JWT, exact HTTPS CORS, persistent storage, selector, ClamAV, YARA and resource configuration intact. Public URL is `https://xai-compress.vercel.app`; verified portal is `https://portal-xai.vercel.app`; backend remains `https://xai-1-be9s.onrender.com`.
5. Deploy the reviewed backend. Verify `/health`, `/public/status`, and the published routes for `/auth/totp/status`, `/auth/totp/resend`, `/auth/totp/email/confirm`. Confirm unauthenticated enrollment/provisioning requests are rejected. A healthy HTTP process is not evidence of working scanners.
6. Sign into the registered development account `m.taieb2k@gmail.com` and request MFA setup exactly once. Verify provider acceptance separately from actual inbox delivery. Do not print the code. Confirm email, provision the authoritative secret, confirm TOTP, log out and test MFA login.
7. Repeat the requested flow on CPH2307 `816f7f5f`. Do not substitute another device or label mocked tests as physical passes.
8. Run a real compression/history/download round-trip only with healthy production scanners. Brevo's existing .xaic attachment restriction remains; use the supported share/download path instead of renaming artifacts to bypass it.
9. Enable downloads only after signed artifacts are hosted at real verified URLs with version, checksum and installation guidance. Current local Android/Windows packages are test distributions, and no iOS distribution was verified.

Provider request contract: [Brevo transactional send API](https://developers.brevo.com/reference/send-transac-email). The existing Resend provider remains selectable; SMTP remains supported for its previous artifact-email use.
