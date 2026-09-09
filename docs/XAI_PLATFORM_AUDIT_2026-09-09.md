# XAI platform integration and Brevo audit — 2026-09-09

Overall production readiness: **BLOCKED**. Local fixes do not establish live readiness. No deployment, production migration, live email, or target-phone interaction was performed.

## 1. Architecture discovered

FastAPI (`services/api_fastapi`) is authoritative for accounts, password verification, JWT access tokens, rotating opaque refresh tokens, MFA, owner-scoped file history, downloads, sharing and compression. SQLAlchemy models are initialized through `Base.metadata.create_all(engine)` at application import. The existing additive SQL migration creates `totp_enrollments`; no Alembic/versioned migration runner exists.

Flutter mobile (`apps/mobile_authenticator_flutter`) is the enrollment/authenticator client. It unlocks device-protected account storage, signs into the backend, verifies the emailed code, provisions the backend's exact otpauth URI into secure storage, and confirms TOTP. `MainActivity : FlutterFragmentActivity()` is preserved. Its actual Dart configuration key is `XAI_API_URL`, defaulting to `https://xai-1-be9s.onrender.com`.

Angular (`apps/web_angular`) is the authenticated portal. Next.js (`apps/public_nextjs`) is the public site; it links to Angular and does not introduce another account system. Flutter desktop (`apps/desktop_flutter`) supports local engines and cloud operations through the same API. Blazor Server (`apps/admin_dotnet`) holds admin tokens in a scoped server circuit and verifies authorization against `/admin/stats` before retaining a login.

Session synchronization is through backend state, not token sharing between applications. Angular persists its existing token pair in localStorage; mobile and desktop keep backend tokens in memory. Authenticator factors remain in secure storage after account logout, so logging out does not destroy the factor needed for the next MFA login. Admin sessions expire to a sign-in state rather than automatically refreshing. There is no cross-application SSO or global logout protocol.

## 2. Issues found by severity

| Severity | Issue | Result |
| --- | --- | --- |
| CRITICAL | Live scanner unavailable; production still exposes old MFA contract | BLOCKED — requires operational deployment and scanner restoration |
| HIGH | MFA verification supported only Resend despite existing Brevo artifact transport | PASS — Brevo verification uses the existing email module and shared transport |
| HIGH | Concurrent Angular refresh calls raced rotation; failures retained stale auth | PASS — shared in-flight refresh, bounded retry, session clearing and storage-event synchronization |
| HIGH | Backend refresh consumption was a read followed by an unconditional update | PASS — conditional atomic consumption prevents reuse of the same refresh token |
| HIGH | Desktop raw response errors, missing timeouts, stale screen-local login flag | PASS — sanitized transport, finite waits, refresh/logout, account-driven UI |
| HIGH | Admin showed demo incidents and healthy dependencies with demo fallback disabled | PASS — development-only opt-in samples; otherwise unknown/unavailable reporting |
| MEDIUM | Fake portal activity, ineffective settings, no history downloads or error recovery | PASS — real history, downloads, honest settings and error/retry states |
| MEDIUM | Mobile discarded refresh tokens and never revoked on logout | PASS — in-memory rotation and best-effort backend revocation; no factor deletion |
| MEDIUM | Duplicate submissions and unsafe async completion paths | PASS — bounded fixes across portal, mobile, desktop and admin; no claim of exhaustive race verification |
| MEDIUM | Next lint opened an interactive setup prompt | PASS — explicit Next ESLint configuration added |
| MEDIUM | Production website defaults and Angular return link could resolve to localhost | PASS — confirmed production URLs used in production defaults/examples |
| LOW | Downloads claimed signed CI distribution without a workflow | PASS — truthful platform-specific unavailable/test states |

## 3. Exact files modified in this continuation

The workspace already contained earlier MFA edits and unrelated deleted engine/test files. Those changes were preserved. In particular, the pre-existing deletion of `services/api_fastapi/tests/test_production_yara.py` was not caused or restored by this task.

Backend:
- `services/api_fastapi/app/config.py`
- `services/api_fastapi/app/email_service.py`
- `services/api_fastapi/app/main.py`
- `services/api_fastapi/app/mfa.py`
- `services/api_fastapi/tests/test_brevo_email.py` (new)
- `services/api_fastapi/tests/test_cross_app_contract.py` (new)
- `services/api_fastapi/tests/test_mfa_limits.py`
- `services/api_fastapi/tests/test_production_integration.py`
- `services/api_fastapi/tests/test_security_scanner.py`
- `services/api_fastapi/.env.example`

Mobile:
- `apps/mobile_authenticator_flutter/lib/services/api_service.dart`
- `apps/mobile_authenticator_flutter/lib/core/app_state.dart`
- `apps/mobile_authenticator_flutter/lib/widgets/mfa_setup.dart`
- `apps/mobile_authenticator_flutter/test/session_test.dart` (new)

Desktop:
- `apps/desktop_flutter/lib/services/api_service.dart`
- `apps/desktop_flutter/lib/core/app_state.dart`
- `apps/desktop_flutter/lib/screens/receive_screen.dart`
- `apps/desktop_flutter/lib/screens/settings_screen.dart`
- `apps/desktop_flutter/test/session_test.dart` (new)

Angular:
- `apps/web_angular/src/app/core/auth.service.ts`
- `apps/web_angular/src/app/core/auth.interceptor.ts`
- `apps/web_angular/src/app/pages/compress.page.ts`
- `apps/web_angular/src/app/pages/dashboard.page.ts`
- `apps/web_angular/src/app/pages/files.page.ts`
- `apps/web_angular/src/app/pages/inbox.page.ts`
- `apps/web_angular/src/app/pages/login.page.ts`
- `apps/web_angular/src/app/pages/register.page.ts`
- `apps/web_angular/src/app/pages/settings.page.ts`
- `apps/web_angular/src/app/pages/shares.page.ts`
- `apps/web_angular/src/environments/environment.prod.ts`
- Ignored generated `environment.vercel.ts` was regenerated by the existing build script with confirmed URLs.

Public website:
- `apps/public_nextjs/.eslintrc.json` (new)
- `apps/public_nextjs/.env.example`
- `apps/public_nextjs/lib/deployment.ts`
- `apps/public_nextjs/next.config.ts`
- `apps/public_nextjs/app/downloads/page.tsx`
- `apps/public_nextjs/app/status/page.tsx`

Admin:
- `apps/admin_dotnet/Services/AdminSession.cs`
- `apps/admin_dotnet/Services/PlatformApiClient.cs`
- `apps/admin_dotnet/Program.cs`
- `apps/admin_dotnet/appsettings.json`
- `apps/admin_dotnet/Components/Layout/MainLayout.razor`
- `apps/admin_dotnet/Components/Pages/Login.razor`
- `apps/admin_dotnet/Components/Pages/Home.razor`
- `apps/admin_dotnet/Components/Pages/Users.razor`
- `apps/admin_dotnet/Components/Pages/Jobs.razor`
- `apps/admin_dotnet/Components/Pages/Audit.razor`
- `apps/admin_dotnet/Components/Pages/Incidents.razor`
- `apps/admin_dotnet/Components/Pages/Quarantine.razor`

Configuration/documentation:
- `.env.example`
- `deployment/.env.render.api.example`
- `deployment/.env.vercel.public.example`
- `docs/XAI_PLATFORM_AUDIT_2026-09-09.md` (this report)
- `deployment/BREVO_MFA_ROLLOUT.md` (new)

## 4. Dependencies

No runtime dependency or lockfile was added, removed or upgraded. Brevo uses the existing Python standard-library HTTP transport. The already-declared `yara-python==4.5.4` was installed only into `scratch/audit-python-deps` for this machine's backend tests. .NET restore completed. Flutter and JavaScript builds used their existing dependencies.

The first YARA run failed because the package was absent; the sandbox then refused native DLL loading. Running the installed dependency with normal access resolved those failures. Next lint remains the installed Next 15 command and emits its deprecation notice; explicit configuration prevents interactive setup.

## 5. Brevo implementation

`EMAIL_PROVIDER=brevo` selects backend-only `POST https://api.brevo.com/v3/smtp/email`, with `api-key` header, configured sender name/email, authenticated user's registered email in `to`, and `textContent`. A successful submission requires HTTP 201 and a nonempty string `messageId`. The finite timeout is the existing `SMTP_TIMEOUT_SECONDS` setting. No new parallel email infrastructure or client dependency was introduced.

Messages contain XAI Compress branding, the verification code, a maximum ten-minute expiry statement and a warning not to share it. No TOTP secret, URI, password, application token or provider key is placed in the email. The recipient is not hardcoded. Resend and existing SMTP artifact support remain; SMTP is not an MFA-verification provider. Unknown provider values fail with a fixed configuration error.

Timeout, connection errors, 401/403, other 4xx, 429, 5xx, invalid JSON, non-object JSON and missing/empty message IDs fail safely. Provider response bodies are not exposed. There are no automatic email retries that could cause duplicate messages. The existing `.xaic` attachment restriction for Brevo is preserved; secure share/download is the alternative.

Official contract: [Brevo transactional send API](https://developers.brevo.com/reference/send-transac-email), [transactional email guide](https://developers.brevo.com/docs/send-a-transactional-email).

## 6. MFA implementation state

PASS — automated local coverage. Backend generates the Base32 secret; the expiring single-use email code is hashed; authorized email confirmation consumes it before secret disclosure; TOTP must verify against the same pending secret before activation. Pending, expired and lost-disclosure cases provide restart/retry recovery. Existing attempt/resend bounds remain. Resend responses now report the actual remaining code lifetime, including enrollment expiry.

BLOCKED — production still lacks `/auth/totp/status`, `/auth/totp/resend`, and `/auth/totp/email/confirm` in its published OpenAPI schema. No live enrollment request was sent to the older deployment.

## 7. Backend/client API compatibility

| Contract | Clients/use | Result |
| --- | --- | --- |
| POST `/auth/register`, `/auth/login` | Email/password, optional `totp_code`; backend requires TOTP only after activation | PASS — local tests/source |
| POST `/auth/refresh`, `/auth/logout` | JSON `refresh_token`; rotation/revocation | PASS — regression tests |
| GET `/auth/me`, `/auth/totp/status` | Bearer token; safe state | PASS locally; new status route BLOCKED live |
| POST MFA enrollment/resend/email-confirm/TOTP-confirm | Existing state machine; no client-authored authoritative secret | PASS locally; BLOCKED live |
| POST `/compression/jobs` | Multipart `upload`, synchronous file/job response | PASS — source and mocked integration tests |
| POST `/compression/decompress` | Multipart `upload`, binary restored file | PASS — source and mocked integration tests |
| GET `/history`, `/files/{id}/download` | Owner-scoped history and binary download | PASS — backend tests; UI interaction NOT TESTED |
| POST `/shares`, `/shares/redeem`, `/shares/download` | Existing share contract, no invented polling routes | PASS — source inspection |
| GET `/admin/stats`, `/admin/users`, `/admin/jobs`, `/admin/audit` | Admin authorization | PASS — backend tests/source; authenticated live UI NOT TESTED |

Expired protected requests retry once after a shared refresh in Angular/mobile/desktop. Failed refresh clears local backend session. Admin requires login again on 401/403. Logout clears local state immediately/before waiting for revocation. A network failure cannot guarantee server-side revocation; existing access JWTs remain valid until their configured expiry. Global immediate logout is not implemented by this backend.

## 8–12. Application validation

Final command results are recorded in the validation table below. Mobile MFA widget coverage uses mocked secure storage/biometrics; it is not device evidence. Desktop's live cloud test remains opt-in and skipped because the target production scanner is unavailable. Admin has no test project. Angular has no test architect/runner configured despite a `test` script; `npm test -- --watch=false` fails with `Unknown argument: watch`.

## 13. Website login/navigation

PASS — read-only HTTP checks: public site, `/downloads`, portal root, `/login`, and `/register` returned HTTP 200. The live site's actual links identify `https://portal-xai.vercel.app`; this address was verified rather than invented. Public site remains `https://xai-compress.vercel.app`. No real admin deployment URL was established, so none was invented.

BLOCKED — browser runtime reports no available browser, confirmed by an empty browser list. No visual, keyboard, responsive-layout, or authenticated browser interaction PASS is claimed.

## 14. Website downloads

PASS — source now labels Android and Windows as local test builds, with disabled download buttons and no fabricated release URLs. iOS is unavailable pending Apple's signing/distribution workflow. No local Windows path or repository build directory is linked publicly. No GitHub Releases upload or static hosting was performed. The existing `scripts/build_production.ps1` builds/packages locally and writes checksum/signing manifests; it is not a hosted release pipeline. `.github/workflows` is absent.

## 15. Required environment

Backend-only Brevo configuration:

```dotenv
EMAIL_PROVIDER=brevo
BREVO_API_KEY=<operator enters privately in Render>
BREVO_SENDER_EMAIL=m.taieb2k@gmail.com
BREVO_SENDER_NAME=XAI Compress
SMTP_TIMEOUT_SECONDS=30
```

`BREVO_API_KEY` was not requested, read from the IDE CSV, printed, or embedded in a client. The operator's secret entry remains manual. Sender fields are now separate from SMTP artifact settings. Resend remains optional through `RESEND_API_KEY` and `RESEND_FROM_EMAIL` when selected.

Existing production requirements remain: `APP_ENV=production`, configured `DATABASE_URL` using `postgresql+psycopg://`, random `JWT_SECRET`, exact HTTPS `CORS_ORIGINS`, `PUBLIC_BASE_URL`, persistent `STORAGE_PATH`, `SELECTOR_MODEL_PATH`, `SECURITY_SCAN_REQUIRED=true`, real `CLAMAV_HOST`/`CLAMAV_PORT`, production `YARA_RULES_PATH`, and the resource settings already defined in `config.py`/Render example. No scanner bypass was added. `SMTP_MAX_ATTACHMENT_BYTES` applies to artifact email; SMTP credentials are required only for SMTP artifact delivery.

Public site: `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_APP_URL`, server-only `INTERNAL_API_URL`. Angular Vercel generator: `XAI_API_URL`, `NEXT_PUBLIC_SITE_URL`, optional `ADMIN_URL`. Both Flutter clients: `--dart-define=XAI_API_URL=https://xai-1-be9s.onrender.com`. Admin: `PlatformApi__BaseUrl`; demo fallback remains false in production.

## 16. Migration

PASS — existing migration test executes `migrations/001_totp_enrollments.sql` twice on SQLite and preserves an existing active user's factor. BLOCKED — PostgreSQL/Render application has not been performed or verified.

From the backend directory in the configured Render runtime, the equivalent narrowly scoped command is:

```sh
python -c "from app.db import engine; from app.models import TotpEnrollment; TotpEnrollment.__table__.create(engine, checkfirst=True)"
```

This creates only the additive enrollment table. Alternatively execute the checked-in SQL through the operator's PostgreSQL migration tooling. The existing startup `create_all` also creates missing tables if its database user has permissions, but there is no versioned migration record/predeploy command. Explicitly apply and verify the table before rollout. Do not reset tables, recreate users or expose the database URL on a command line.

## 17. Automated test results and limitations

| Check | Result | Evidence |
| --- | --- | --- |
| Full backend suite | PASS | 90 passed, 177 dependency/deprecation warnings; real YARA, mocked ClamAV/provider/engine boundaries |
| Complete combined logical scenario | PASS | 1 additional test passed: Brevo email confirmation, MFA login, compression, history, download and logout; external services mocked |
| Mobile analyze | PASS | No issues found after removing one unused test import |
| Mobile tests | PASS | 15 passed, including concurrent refresh and logout |
| Android debug package | PASS | `flutter build apk --debug --dart-define=XAI_API_URL=https://xai-1-be9s.onrender.com` produced `app-debug.apk` |
| Desktop analyze | PASS | No issues found |
| Desktop tests | PASS | 4 passed; 1 opt-in live test skipped |
| Windows release build | PASS | Final incremental build also passed; built `build/windows/x64/runner/Release/xai_compress_desktop.exe`; unsigned |
| Angular production build | PASS | Normal production build passed with compiler filesystem access |
| Angular Vercel build | PASS | Final portal code built using verified API/public URLs |
| Angular test command | FAIL | No test architect configured; `Unknown argument: watch` |
| Next.js lint/typecheck/build | PASS | Lint clean; TypeScript check and 14-page production build passed |
| Final download-page rebuild | PASS | Final platform-specific download page compiled, typechecked and generated successfully |
| Admin restore/build | PASS | net8.0 output; zero warnings/errors |
| Admin tests | NOT TESTED | No test project exists |
| SQL migration repeatability | PASS | SQLite test only; production PostgreSQL BLOCKED |
| Scoped git diff whitespace check | PASS | No whitespace errors |
| Visual/browser UX | BLOCKED | Browser discovery returned no available browser |

Android emitted a `mobile_scanner` Kotlin Gradle compatibility warning and an SDK XML tooling-version warning. They did not fail this build; future toolchain upgrades require compatibility review. No dependency was blindly upgraded. New local artifact sizes and SHA-256 values are recorded in `scratch/audit-built-artifacts.json`; no artifact was uploaded.

The later backend rerun initially had 13 failures/77 passes because concurrent builds left 8.92 GiB free on C:, below the normal approximately 9 GiB admission reserve. The guard correctly returned 503. The tiny-file integration fixture now sets 1 MiB upload/restoration limits and a 16 MiB reserve for tests only. Production settings are unchanged, and dedicated resource-guard tests still explicitly verify low disk, concurrency, timeout and upload rejection.

## 18–20. Live email, end-to-end and physical phone

| Check | Result | Evidence/blocker |
| --- | --- | --- |
| BREVO REQUEST | BLOCKED | Updated backend is not deployed; no real submission made |
| BREVO ACCEPTED | BLOCKED | No real provider message ID |
| EMAIL DELIVERY | NOT TESTED | Inbox receipt not observed |
| VERIFICATION CODE | NOT TESTED | No live challenge generated or received in this task |
| Full MFA E2E | BLOCKED | Production lacks email-verification routes |
| Register/login/enroll/confirm/logout logical flow | PASS | Isolated backend and Flutter mock tests only |
| Compression/history/download logical compatibility | PASS | Backend tests and source inspection; scanner daemon mocked |
| Real compression round-trip | BLOCKED | Production security scanner unavailable |
| Target CPH2307 installation/startup/biometrics | BLOCKED | ADB lists only `43190DLJH0017A`, not `816f7f5f` |
| Target registration/login/email/provisioning/TOTP/MFA login | BLOCKED | Required device absent and live backend flow unavailable |
| Target secure storage/navigation/logout/stays-running | BLOCKED | No target-device interaction performed |

No other connected phone was used as a substitute. No code or credential was displayed.

## 21. Artifacts/signing

Both existing manifests were checked against actual file bytes before builds:

| Platform | Existing artifact | Version | Size | Checksum verification | Classification |
| --- | --- | --- | --- | --- | --- |
| Android | `apps/mobile_authenticator_flutter/build/app/outputs/flutter-apk/app-release.apk` | source `0.1.0+1` | 67,042,288 bytes | PASS — matches Android manifest | Debug-signed test artifact, not production |
| Windows | `E:/GradleCache/xai-desktop-build/xai-windows-20260908-162959.zip` | source `0.1.0+1` | 12,258,005 bytes | PASS — matches Windows manifest | Unsigned test distribution |
| iOS | No verified artifact | Not verified | — | NOT TESTED | BLOCKED — macOS/Xcode/Apple signing/distribution |

Source version is not independent package-metadata verification. Updated build results are in the validation table; existing ZIP/APK manifests do not certify newly built output. Signing configuration rejects release Android builds without configured keystore credentials unless debug signing is explicitly opted into. No signing key was created or inspected.

## 22. Production security

PASS — `/health` and `/public/status` HTTP 200; health reports selector present. FAIL — public scanner readiness reports `unavailable`; overall status `degraded`, notifications `degraded`. Health alone does not establish compression readiness. ClamAV/YARA enforcement, file validation and production resource limits were not weakened.

PASS — scoped recognizable credential-pattern scan found no Brevo/Resend key or private-key PEM matches in tracked application/backend/deployment text. Root `.env` is not tracked. This is not a comprehensive secret-history audit. No client email-provider integration was added. Existing SQL parameters remain hidden; token/secret response bodies are not logged by the new transport code.

## 23. Remaining blockers

1. Deploy reviewed backend/client changes only after required local checks pass; apply/verify PostgreSQL migration.
2. Operator configures backend-only Brevo credentials and verified sender; perform exactly one authorized real MFA email test, then confirm inbox receipt without displaying the code.
3. Restore production ClamAV/YARA availability and verify fail-closed behavior and storage persistence.
4. Reconnect CPH2307 (`816f7f5f`) and complete the specified physical MFA/navigation/logout flow.
5. Provide signed, versioned, verified hosted artifacts before enabling public downloads. iOS needs Apple tooling and distribution.
6. Complete browser UX and authenticated cross-app live integration when a browser is available. Angular's missing test runner and absent admin test project remain coverage limitations.
7. Existing Angular localStorage tokens and stateless access-token expiry are architectural limitations, not newly introduced SSO/global logout guarantees. MFA factor encryption at rest and broader authentication abuse controls were not certified in this audit.

**Do not label this platform production-ready on the basis of local tests.**
