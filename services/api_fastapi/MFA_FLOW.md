# XAI account and authenticator flow — implementation and validation

## Confirmed original cause

The mobile app's former `AppState.addManual` accepted an arbitrary Base32 string
and wrote it only to `FlutterSecureStorage`. It did not enroll the logged-in backend
user. The existing backend `POST /auth/totp/enroll` (previously main.py:86–92)
independently generated a secret using `pyotp.random_base32()` and returned it
immediately. A code derived from an invented local secret could not authenticate
against the backend's different secret. The mobile API enrollment methods existed
but were not connected to a registration/login/setup UI.

The original backend already had `/auth/register`, `/auth/login`, `/auth/me`,
`User.totp_secret`, `User.totp_enabled`, pyotp verification with `valid_window=1`,
and SQLAlchemy `Base.metadata.create_all`. There was no email enrollment challenge
or migration framework. The email abstraction supported SMTP/Brevo artifacts.
The quoted optional-TOTP label and old immediate-QR enrollment UI were in Angular.

## Resulting contract

| Endpoint | Behavior |
| --- | --- |
| POST /auth/register | Existing account registration and token response retained. |
| POST /auth/login | Password required. TOTP required only when `totp_enabled`; same authoritative stored secret, unchanged +/- one time-step window. Malformed stored factor fails closed with a fixed diagnostic. |
| GET /auth/me | Existing safe user metadata and MFA-enabled flag; no secret. |
| GET /auth/totp/status | Authenticated safe state, email, enrollment ID; no code, secret, URI, or hash. |
| POST /auth/totp/enroll | Authenticated, optional `{ "restart": false }`; generate backend secret, persist pending enrollment and send email challenge. Extra client fields are rejected. Active MFA cannot be overwritten. |
| POST /auth/totp/resend | Authenticated; replace unused email challenge for an undisclosed, unexpired enrollment. |
| POST /auth/totp/email/confirm | Authenticated `{ "enrollment_id": "...", "code": "..." }`; consume email code and return pending secret + otpauth URI once. `Cache-Control: no-store`. |
| POST /auth/totp/confirm | Same body shape; require prior email confirmation and correct TOTP, copy pending factor into existing User fields, then clear pending secret/hash. Completed enrollment cannot be replayed. |

Registration and login validation responses do not echo request values. SQLAlchemy
exception parameters are hidden. Enrollment email recipients always come from the
authenticated User record, never a client-selected address. No test recipient is
hardcoded into business logic.

## Enrollment controls and recovery

- Email code: six random decimal digits, 10-minute maximum lifetime, keyed HMAC
  storage using the backend JWT secret with an enrollment-specific context.
- Five failed attempts per email challenge and five failed TOTP attempts per
  enrollment. One email per 60 seconds; at most five per user per hour, including
  restarts. Pending enrollment expires after 20 minutes.
- Database user-row updates serialize enrollment mutations across workers on
  PostgreSQL and SQLite. Successful email consumption commits before disclosure.
- Delivery failure does not enable MFA or reveal the secret. The persisted pending
  request can be inspected and resent after the cooldown. Provider acceptance does
  not mean the email reached the inbox.
- If a one-time response is lost, explicit restart invalidates the pending secret.
  If local secure storage fails, Flutter retains the response in memory for a save
  retry. Closing the page before saving requires restarting setup.
- Starting new enrollment clears legacy *unconfirmed* User secret material.
  Existing active MFA factors remain unchanged. Legacy unconfirmed clients must
  restart through the new email flow.
- No new at-rest encryption scheme was introduced: active and pending factors use
  the existing database's protection model. Database/backup access controls remain
  an operator responsibility.

## Resend and environment

Backend configuration requires:

```dotenv
EMAIL_PROVIDER=resend
RESEND_API_KEY=<set privately in the backend secret environment>
RESEND_FROM_EMAIL=<sender permitted by the Resend account>
```

The implementation uses the official HTTPS `POST https://api.resend.com/emails`
with Bearer authentication. Verification email subject is **XAI Authenticator
verification**. Its body contains only a verification code and instructions, never
TOTP secret, URI, password, or application tokens. Provider response bodies are
not returned or logged. The documented testing-recipient restriction is classified
and reported without echoing the recipient/account details.

Official references: [Send Email](https://resend.com/docs/api-reference/emails/send-email)
and [Resend test-domain restriction](https://resend.com/docs/knowledge-base/403-error-resend-dev-domain).

Resend also extends the existing artifact transport abstraction so changing the
provider does not select an unsupported transport. Attachment bytes and size checks
are preserved. Compression, scanner enforcement, and SMTP/Brevo behavior were not
changed. Resend account sender verification and actual delivery remain untested.

## Database migration

`migrations/001_totp_enrollments.sql` adds only `totp_enrollments`, keyed by user ID.
It records the pending secret, enrollment ID, challenge hash, expiry, disclosure,
attempt counters, and resend limits. It does not alter or drop existing tables.
The new model participates in existing `create_all` startup for fresh/local DBs.
Apply the additive SQL migration before production rollout. It was tested twice
on SQLite against an existing active user and preserved the active factor. It
has **not** been executed against production PostgreSQL.

## Flutter and Angular

Flow: local device unlock → sign in/create account → Setup Authenticator → email
verification → direct secure provisioning → current TOTP confirmation → MFA enabled.
Existing local codes are visible after device unlock so the user can sign in with
MFA already enabled. Access tokens remain in memory only. Lock/sign-out clears them.

Manual secret entry was removed. Existing otpauth parsing and secure storage are
reused. Successful new provisioning replaces earlier app-provisioned entries for
the same email; the setup UI displays the code for the current enrollment explicitly.
Storage reads/writes have 15-second bounds, HTTP requests 40 seconds, and device
authentication 90 seconds. Failures clear loading states and expose retry/status/
restart actions. Local deletion explains that it does not disable server-side MFA.

Angular's security page directs enrollment to the mobile flow and can refresh MFA
status without fetching secrets. Its login guidance explicitly distinguishes
disabled/pending MFA from enabled MFA. Old immediate-secret API calls were removed.

The verified Dart environment key remains `XAI_API_URL`. Both default modes now
resolve to `https://xai-1-be9s.onrender.com`; release HTTPS validation remains.
`MainActivity : FlutterFragmentActivity()` is preserved, not modified by this task.

## Automated validation — 2026-09-09

- `flutter analyze`: PASS, no issues.
- `flutter test`: PASS, 13 tests, including device-unlock navigation, setup,
  registration/login UI, invalid email/TOTP, provisioning, configured state,
  backend failure, storage retry, lost disclosure and finite network timeout.
- `python -m pytest tests/test_mfa_enrollment.py tests/test_mfa_limits.py tests/test_health.py tests/test_integration_boundaries.py -q -p no:cacheprovider --disable-warnings`:
  PASS, 24 tests. Tests use an isolated SQLite database and mocked Resend. Existing
  dependency deprecation warnings remain. No production database was used.
- `npm.cmd run build -- --configuration development` in `apps/web_angular`:
  PASS. The initial sandboxed build failed source resolution; the approved build
  outside that restriction completed successfully.
- Scoped `git diff --check`: PASS.

## Real email and physical device — blocked, not passed

Safe local preflight reported exactly these missing configuration entries:
`EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`.
Per the request, the real delivery test stopped here. **No real email was sent.**
The key was neither requested nor printed. This does not inspect Render's private
environment and therefore does not assert which secrets are configured remotely.

Attempted command:

```powershell
flutter run -d 816f7f5f --dart-define=XAI_API_URL=https://xai-1-be9s.onrender.com
```

Result: `No supported devices found with name or id matching '816f7f5f'.`
ADB lists a Pixel 8 (43190DLJH0017A), not CPH2307. No substitute phone was used.

| Requested physical check | Result for this new flow |
| --- | --- |
| APP STARTUP | BLOCKED — target phone absent |
| BIOMETRIC UNLOCK | BLOCKED — target phone absent |
| ACCOUNT LOGIN | BLOCKED — live flow not run |
| MFA SETUP REQUEST | BLOCKED — new backend not deployed/tested live |
| RESEND EMAIL DELIVERY | BLOCKED — missing local Resend configuration |
| EMAIL CODE VERIFY | BLOCKED — no live email challenge |
| AUTHENTICATOR PROVISION | BLOCKED — target phone absent |
| TOTP VERIFY | BLOCKED — live flow not run |
| MFA LOGIN | BLOCKED — live flow not run |
| SECURE STORAGE | BLOCKED — tested with mocks only in this task |
| APP NAVIGATION | BLOCKED — widget tests pass; new physical flow not run |
| APP STAYS RUNNING | BLOCKED — new physical flow not run |

The earlier successful physical unlock from the previous task is not evidence for
this new enrollment flow. Production deployment, the additive migration, verified
Resend sender, one real delivery test to m.taieb2k@gmail.com, and reconnection of
CPH2307 remain required. The complete flow must then pass with a real account.
No release was built. Production signing, live scanner availability, production
email delivery and complete MFA validation are not certified; this is **not a
production-ready claim**.

## Exact task file inventory

Modified:

- `services/api_fastapi/.env.example`
- `services/api_fastapi/app/config.py`
- `services/api_fastapi/app/db.py`
- `services/api_fastapi/app/email_service.py`
- `services/api_fastapi/app/main.py`
- `services/api_fastapi/app/models.py`
- `services/api_fastapi/app/schemas.py`
- `apps/mobile_authenticator_flutter/README.md`
- `apps/mobile_authenticator_flutter/lib/core/app_state.dart`
- `apps/mobile_authenticator_flutter/lib/main.dart`
- `apps/mobile_authenticator_flutter/lib/screens/home_screen.dart`
- `apps/mobile_authenticator_flutter/lib/screens/lock_screen.dart`
- `apps/mobile_authenticator_flutter/lib/services/api_service.dart`
- `apps/mobile_authenticator_flutter/lib/services/biometric_service.dart`
- `apps/mobile_authenticator_flutter/lib/services/deployment_config.dart`
- `apps/mobile_authenticator_flutter/lib/widgets/account_code_card.dart`
- `apps/mobile_authenticator_flutter/test/widget_test.dart`
- `apps/web_angular/src/app/core/api.service.ts`
- `apps/web_angular/src/app/pages/login.page.ts`
- `apps/web_angular/src/app/pages/security.page.ts`

Added:

- `services/api_fastapi/app/mfa.py`
- `services/api_fastapi/migrations/001_totp_enrollments.sql`
- `services/api_fastapi/tests/test_mfa_enrollment.py`
- `services/api_fastapi/tests/test_mfa_limits.py`
- `apps/mobile_authenticator_flutter/lib/widgets/mfa_setup.dart`
- `apps/mobile_authenticator_flutter/test/mfa_flow_test.dart`
- `services/api_fastapi/MFA_FLOW.md` (this report)

Unrelated pre-existing working-tree changes were not included in this task.
