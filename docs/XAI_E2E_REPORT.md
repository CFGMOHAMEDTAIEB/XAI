# XAI real integration validation - 2026-09-06

**Overall result: FAIL / incomplete external and browser stages.** The real local API, Android TOTP, compression and decompression chain passed. No email was sent or received, and no browser UI upload was performed. This report does not substitute API tests for the requested full application scenario.

## Actual architecture

```mermaid
flowchart TD
  Portal[Angular portal localhost:4200] -->|nginx /api proxy| API[FastAPI localhost:8000]
  Desktop[Flutter desktop] -->|local subprocess| LocalEngine[Python XAI engine]
  Desktop -->|login / history / share metadata| API
  Public[Next.js localhost:3000] -->|public share metadata; backend:8000| API
  Admin[.NET admin localhost:5050] -->|authenticated administration; backend:8000| API
  API --> DB[(PostgreSQL db:5432)]
  API --> Storage[(xai-storage volume /data)]
  API --> Engine[Hybrid V3 / hybrid-v2 mode / Selector V2 top-3]
  API -->|QR or manual enrollment seed| Mobile[XAI Flutter authenticator]
  Mobile -->|locally generated 6-digit TOTP entered in client| API
  API -.->|new SMTP attachment route; not configured| SMTP[SMTP provider]
  SMTP -.-> Mailbox[m.taieb2k@gmail.com]
  Mailbox -.->|manual saved attachment import; not verified| Portal
  Portal -->|POST /compression/decompress| API
  Engine --> Restored[Restored bytes + SHA-256]
```

The mobile UI imports QR/manual secrets and generates TOTP locally. Its HTTP service exists, but normal code generation does not call it. The actual authentication exchange is enrollment from backend, code generation on mobile, and code verification by backend during confirmation/login. Authentication uses password hashes, JWT access tokens, database-backed refresh tokens, and optional TOTP. No new authentication mechanism was introduced.

There is no Gmail API, IMAP, inbound webhook, or mailbox-retrieval implementation. The existing desktop decompression flow accepts local files; the new Angular Inbox imports a manually saved attachment. Every imported attachment is treated as untrusted regardless of sender. No spoofing or sender impersonation was performed. Share-code redemption remains a metadata operation; the new explicit email action sends an attachment independently of share-code creation.

Keycloak, MinIO, malware scanners, Redis workers, and monitoring described elsewhere are not services in the active Compose pipeline. Compression executes synchronously inside FastAPI. The public status page is declared development status, not live monitoring. Desktop local-engine UI and .NET authenticated administration were not exercised end to end in this run.

## Services and connection evidence

| Connection | Address / contract | Result |
|---|---|---|
| Host to API | http://localhost:8000/health | HTTP 200; selector present |
| Portal to API | http://localhost:4200/api; nginx to backend:8000 | Real registration, multipart upload, download, decompression pass |
| Android to API | http://10.0.2.2:8000/health | HTTP 200 from pixel_emulator |
| Backend to database | PostgreSQL db:5432 | Real user, job and audit records committed |
| Backend to engine | /opt/xai-compress; frozen selector JSON and configs | Real XAIC v6 artifact; verified round trip |
| Backend to storage | /data named volume | Original/artifact generated; restored bytes served |
| Next.js to API | http://backend:8000 | HTTP 200 from inside Next.js container |
| Next.js public URL | http://localhost:3000 | HTTP 200 |
| .NET public URL | http://localhost:5050 | HTTP 200; authenticated admin flow unverified |
| Backend to SMTP | Environment-driven SMTP with STARTTLS or implicit TLS | Not configured; external action blocked |
| Mailbox to importer | Manual saved .xaic; E2E script accepts actual .eml export | Implementation added; real receipt unverified |

All five Docker services are running. PostgreSQL and backend report healthy. Only backend and Angular images were rebuilt/recreated; dependency layers were reused and database/storage volumes retained. Final nginx configuration test passed. A transient 502 immediately after backend recreation cleared once health became ready; both direct container DNS access and proxy health then passed.

### HTTP contracts exercised / implemented

- `POST /auth/register`: JSON email/password; test-only disposable accounts created.
- `POST /auth/login`: JSON email/password/totp_code; access and refresh tokens returned. Missing code rejected with 401 after MFA enrollment.
- `POST /auth/totp/enroll`: Bearer token; QR PNG, otpauth URI and secret. Active enrollment replacement now rejects with 409.
- `POST /auth/totp/confirm`: Bearer token and JSON `{ "code": "123456" }`. Updated clients no longer put codes in URL query strings.
- `POST /compression/jobs`: Bearer token and multipart field `upload`; job ID, sizes, SHA-256 and integrity flag returned.
- `GET /files/{id}/download`: Bearer token and ownership check; attachment with `application/octet-stream` and `.xaic` filename.
- `POST /files/{id}/email`: Bearer token and JSON recipient_email; verified owner artifact attached. Success means SMTP acceptance, never proof of receipt. Missing settings return 503; provider errors return 502 without credentials in the response.
- `POST /compression/decompress`: Bearer token and multipart `upload`; lossless container validation, upload/output limits, engine checksum validation, restored attachment and `X-Content-SHA256` header. Invalid input returns 400; excessive input returns 413. Temporary decompression files are removed after response completion or failure.

nginx now permits 1024 MiB requests and allows 600 seconds for upstream processing. Backend upload and restored-output defaults are 1 GiB. Multipart overhead means nginx's effective maximum file size is slightly below its total request limit. SMTP attachment default limit is 18,000,000 bytes. The repeatable HTTP test uses a 600-second timeout; SMTP uses a 30-second timeout.

## Problems found, root causes, and fixes

| Finding | Evidence / root cause | Fix |
|---|---|---|
| Real compression could not start | HTTP 500: missing `/opt/xai-compress/configs/hybrid_profiles.json` | Copy existing engine configs into backend image |
| Portal rejected normal larger uploads | Actual >1 MiB request returned nginx HTTP 413 | Align nginx request limit with backend and extend proxy timeouts |
| No email transport | Shares returned `not_configured_in_mvp`; no SMTP/provider code | Add explicit authenticated SMTP attachment endpoint and configuration |
| No portal attachment receive/decompress flow | Inbox only redeemed metadata | Add manual .xaic import, backend validation and restored-file download |
| No portal artifact download after compression | Completion text discarded job ID | Retain job ID and expose real artifact download |
| No portal enrollment UI | Security page was static overview | Add backend QR/manual enrollment display and mobile-code confirmation |
| Active TOTP could be silently replaced | Enrollment reset secret and disabled MFA | Reject enrollment when MFA is already enabled |
| Confirmation codes in URLs | Both clients used `?code=...` | Move confirmation to validated JSON body in backend and clients/docs |
| Unsafe/unbounded decompression staging | Unlimited copy; upload-derived output path could collide with input path | Bounded copy, fixed internal paths, sanitized output name, format check and engine output limit |
| Failed jobs/temp files could remain | Cleanup was missing or occurred while source was open | Close upload before cleanup; remove failed compression and decompression work |
| Mobile widget test was obsolete | ProviderNotFoundException; expected starter counter | Test actual locked authenticator with AppState provider |

No engine algorithm was replaced or altered. Existing Flutter SDK, secure storage/local-auth migrations, E: Gradle cache and build junction were preserved. The workspace already contained extensive changes before this task; those were not reset, staged or committed.

## Files changed by this task

| File | Exact task change |
|---|---|
| `.env.example` | Document SMTP host/port/username/password/from/security placeholders |
| `docker-compose.yml` | Pass SMTP configuration into backend |
| `services/api_fastapi/Dockerfile` | Include engine configs directory |
| `services/api_fastapi/app/config.py` | Add SMTP settings/limits and decompressed-output limit |
| `services/api_fastapi/app/email_service.py` | New TLS SMTP transport with actual MIME attachment, size/hash result and missing-config errors |
| `services/api_fastapi/app/schemas.py` | EmailSend and six-digit TotpConfirm request schemas |
| `services/api_fastapi/app/main.py` | Email endpoint; JSON TOTP confirmation; active-factor protection; safe staging and cleanup; decompression limits/validation/hash header |
| `services/api_fastapi/tests/test_integration_boundaries.py` | Eight focused SMTP/filename/upload-limit/cleanup tests |
| `apps/web_angular/nginx.conf` | Upload and upstream timeout limits |
| `apps/web_angular/src/app/core/api.service.ts` | Download, email, decompress, enroll and confirm API calls |
| `apps/web_angular/src/app/core/download.ts` | Browser Blob download helper |
| `apps/web_angular/src/app/pages/compress.page.ts` | Preserve job ID, download artifact, make mandatory integrity verification explicit |
| `apps/web_angular/src/app/pages/shares.page.ts` | Explicit email attachment action and delivery/error feedback |
| `apps/web_angular/src/app/pages/inbox.page.ts` | Manual untrusted attachment import and validated decompression/download |
| `apps/web_angular/src/app/pages/security.page.ts` | Real TOTP enrollment/confirmation UI |
| `apps/mobile_authenticator_flutter/lib/services/api_service.dart` | Send confirmation code in JSON body |
| `apps/mobile_authenticator_flutter/test/widget_test.dart` | Replace counter test with authenticator lock-screen regression test |
| `apps/mobile_authenticator_flutter/docs/INTEGRATION.md` | Document new confirmation contract |
| `apps/mobile_authenticator_flutter/README.md` | Document JSON confirmation contract |
| `scripts/test_full_e2e.py` | Repeatable real-service test with human mobile code, real email receipt evidence and UI confirmation |
| `scripts/test_local_pipeline.py` | Local-only real-engine/proxy/invalid-input diagnostic; no email send and no full PASS claim |
| `docs/XAI_E2E_REPORT.md` | This report and operational instructions |

Diagnostic artifacts and temporary diagnostic helpers are under ignored `dist/`. No secrets are embedded in those helper source files or result JSON. Disposable account passwords were generated in memory and not persisted; newly enrolled test accounts remain in the backend and mobile app. No existing accounts were removed.

## Flutter and Android results

- `where.exe flutter`: C:\src\flutter\bin (correct SDK).
- Flutter 3.47.1, Dart 3.13.1.
- `flutter doctor`: Android license status unknown; other reported tooling checks pass. Host reports Windows 10 build 19045, despite the request describing Windows 11.
- `flutter devices`: emulator dynamically discovered as `emulator-5554`.
- AVD name verified as `pixel_emulator`; `sys.boot_completed=1`.
- Installed app `com.example.xai_compress_authenticator` launched and normal Unlock flow used.
- Manual enrollment completed through real UI; displayed TOTP confirmed by real backend.
- Login with mobile code succeeds; login without code fails; active-factor replacement fails.
- The resulting authenticated session compressed and decompressed the original test bytes successfully.
- Final `flutter analyze`: No issues found. Final `flutter test`: all 4 tests passed.
- `build` is still a junction to `E:\GradleCache\xai-mobile-build`; `GRADLE_USER_HOME=E:\GradleCache` used for checks. No AVD/cache move or large new Android build was performed.
- Runtime UI validation used the previously installed mobile build. The modified HTTP confirmation helper is unused by the offline enrollment/code UI; its updated source was analyzed and tested, not repackaged as a new APK.

## Compression and integrity evidence

The real multipart test file is intentionally highly repetitive generated data plus binary byte values; its unusually high ratio is not a general performance claim.

| Measurement | Value |
|---|---|
| Original filename | xai-e2e-original.bin |
| Original size | 2,188,096 bytes |
| Compressed filename | xai-e2e-original.bin.xaic |
| Compressed size | 633 bytes |
| Original/compressed ratio | 3456.7077409162716 : 1 |
| Space saving | 99.97107073912662% |
| Artifact SHA-256 | 28fd99661a18aa6a08400f4d99a8742f53179156e24e7cc2cb4994cfc9767d42 |
| Original SHA-256 | c0692edcc10b25caf67b36834214c7c32929314327f88fb016d7ebb61276c4f9 |
| Restored SHA-256 | c0692edcc10b25caf67b36834214c7c32929314327f88fb016d7ebb61276c4f9 |
| Restored size | 2,188,096 bytes |
| Binary equality | TRUE |

Local restored file: `dist/e2e-diagnostic/restored-xai-e2e-original.bin`. The local diagnostic prefixes its saved filename to distinguish it from the original; API download naming restores the original basename by removing `.xaic`.

Evidence: `dist/e2e-diagnostic/report.json`, `dist/e2e-diagnostic/mobile-report.json`, original, compressed and restored files in that directory. These artifacts came from real upload/download/decompression API requests. The original was not copied into the restored output. This restored file was **not received by email**.

Negative live tests rejected forged extension, truncated container, corrupted footer and cross-account download. Eight final backend boundary tests passed; their SMTP transport is a unit-test mock only. No mocked SMTP result is presented as external delivery. Angular production build passed. E2E script syntax/help and a deliberate unreachable-backend failure were checked; that failure prints `XAI E2E TEST: FAIL` and returns nonzero. The full script has not achieved PASS.

## Email blockers and completion procedure

**Email sent: NO. Email received: NO. Actual received-attachment import: UNVERIFIED.**

The running backend has no `SMTP_HOST`, `SMTP_FROM`, `SMTP_USERNAME`, or `SMTP_PASSWORD`. Host environment also had no email configuration names. At minimum configure SMTP_HOST and SMTP_FROM, plus the provider's required credentials. For authenticated SMTP supply SMTP_USERNAME and SMTP_PASSWORD; choose the provider's SMTP_PORT and SMTP_SECURITY (`starttls` or `ssl`). Gmail SMTP requires an appropriate provider-issued credential for the configured sender, not the recipient's normal password. No credential should be pasted into chat or committed. Put secrets in the existing ignored `.env` or deployment environment, then recreate only backend with `docker compose up -d --no-deps backend`.

The user explicitly approved this one test email to m.taieb2k@gmail.com in the follow-up request. Authorization is granted and will not be requested again for this send. Earlier automatic-review rejections are historical; no mail command executed in those attempts. Current blocker: missing SMTP configuration, not user approval.

No connected browser was available (`browser` discovery returned an empty list). Enable the browser connection in Settings > Computer use to permit real portal interaction, or complete the UI steps manually. No alternative browser automation was used to bypass that limitation.

After mail configuration is supplied:

1. Open http://localhost:4200 and sign in with an existing account. If necessary, register a dedicated account through the existing `/auth/register` API in http://localhost:8000/docs; the portal currently has no registration screen.
2. In Security, enroll TOTP using the real mobile QR/manual flow, confirm its displayed code, then sign out and sign in with a mobile code.
3. In Compress, select the real input file, start compression and download the .xaic artifact; note its File ID.
4. In Share, use that File ID and m.taieb2k@gmail.com, then Email compressed attachment. SMTP acceptance alone is not receipt.
5. In the recipient mailbox, save the actual received attachment and export the original message as `.eml`. Treat the sender as unknown; no trust flag or spoofing is required.
6. In Inbox, import that saved attachment, decompress and compare restored bytes/hash against the original.
7. Run the repeatable script from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/test_full_e2e.py --input dist/e2e-diagnostic/xai-e2e-original.bin --expected-artifact dist/e2e-diagnostic/xai-e2e-original.bin.xaic
```

It prompts privately for account password and the current code displayed on mobile; it does not calculate TOTP locally. It uploads through `http://localhost:4200/api`, compresses, downloads, sends through the SMTP route, pauses for a real mailbox `.eml` export, verifies Message-ID/Received headers/MIME/attachment filename/bytes/hash, imports/decompresses the extracted bytes and checks binary equality. It also requires confirmation of the real portal UI operations. Results go to `dist/full-e2e/report.json`. Only a completed run emits `XAI E2E TEST: PASS`; failure includes the stage/reason and exits nonzero. Mailbox headers are human-exported evidence, not cryptographic proof of sender identity.

For a repeatable local-only diagnostic (no email; no full success claim):

```powershell
.\.venv\Scripts\python.exe scripts/test_local_pipeline.py
```

## Remaining limitations and warnings

- SMTP configuration, real recipient-mailbox receipt, and real portal browser UI verification remain blockers to the requested full scenario.
- No inbox polling service exists; receiving is manual attachment import.
- Optional TOTP remains optional for accounts that have not enrolled, matching the existing architecture. The full E2E runner requires an enrolled account.
- Android license status is unknown; no license acceptance was performed.
- Unit test warnings concern Starlette/httpx compatibility and Python crypt/passlib deprecation.
- No malware-scanning service is active. Container validation checks format, limits and integrity; it does not establish that restored contents are safe to execute.
- The original broad workspace modifications predate this task; no git commit was created.

## Follow-up: explicitly approved email test

The saved artifact was rechecked: 633 bytes; SHA-256 `28fd99661a18aa6a08400f4d99a8742f53179156e24e7cc2cb4994cfc9767d42`. No send was attempted because configuration is absent.

Configuration inspection covered the running backend settings, Windows process/user/machine environments, root application `.env`, backend env-file location, Compose configuration and `/run/secrets`. There are no mounted Docker secrets; Vault is only a planned integration in `infrastructure/vault/README.md`. No configured mail provider or provider API implementation was found. Recipient ownership does not identify a sender/provider account.

| Variable | Current state | Required value/type |
|---|---|---|
| SMTP_HOST | Missing | SMTP hostname supplied by the sender's mail provider |
| SMTP_PORT | 587 | Integer TCP port; keep 587 if the provider uses STARTTLS on it |
| SMTP_FROM | Missing | Sender email address authorized by that provider |
| SMTP_USERNAME | Missing | Provider's SMTP login, usually the sender account address |
| SMTP_PASSWORD | Missing | Provider SMTP password/app password; secret string |
| SMTP_SECURITY | starttls | `starttls` or `ssl`, matching the provider and port |

Store actual values in the ignored root `.env` or deployment environment. Do not put credentials in the report, source, or chat. No provider API key is required by this SMTP implementation. For a provider-authorized unauthenticated relay, username/password may be empty; no such relay is currently configured.

The existing SMTP implementation now uses subject `XAI E2E Compressed Artifact Test`. The repeatable runner accepts `--expected-artifact` and refuses to send if the downloaded artifact differs byte-for-byte from that file. It prints and persists the pre-send SHA-256. The backend image was rebuilt and deployed; all eight boundary tests passed, including the subject and exact MIME attachment bytes. Runner CLI validation passed. No alternate mail service was added. Receiving remains manual import/export; no Gmail/IMAP/API receiver exists. SMTP acceptance, mailbox receipt, received attachment decompression and final received-file hash comparison remain unverified.

XAI FULL END-TO-END SCENARIO: FAIL
