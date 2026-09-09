# XAI product truth, functionality and privacy audit

Audit date: 2026-09-10 Europe/Paris. **OVERALL PRODUCTION READINESS = BLOCKED.** This supersedes any earlier readiness conclusion. Local source corrections and passing tests do not establish deployed product completeness.

This is a source audit with read-only deployed HTTP evidence. Interactive browser testing was unavailable: browser discovery returned no connected browser. Authenticated production flows, physical-device installation and legal/operator decisions remain unverified. The accompanying action/search inventories are discovery evidence, not assertions that every interaction passed. No production deployment, email delivery, database mutation, account creation or artifact publication was performed by the live probes.

## 1. Complete discovered route inventory

See [routes.csv](routes.csv): 54 routes/screens/states across Next.js, Angular, .NET, mobile and desktop, including purpose, data source, authorization, functionality status, production URL and issues. [backend-routes.json](backend-routes.json) lists 27 source API routes. Framework metadata/fallback routes, Angular redirects, native enrollment states and the local-factor deletion confirmation are included.

Next.js: `/`, `/architecture`, `/contact`, `/docs`, `/download`, `/downloads`, `/pricing`, `/privacy`, `/security`, `/share/[code]`, `/status`, `/terms`, robots, sitemap and framework not-found handling. `/download` was missing and now redirects locally to `/downloads`. Share pages are deliberately outside navigation and sitemap. Angular has nine page components plus root and wildcard redirects. Admin has dashboard, login, users, jobs, audit, incidents, quarantine, system, error, privacy and liveness. Mobile is an authenticator, not a compression client. Desktop has five navigation destinations and its shell/account subflows.

Orphan/duplicate observations: `/download` is now an alias, not a second distribution system. `DemoAdminData.cs` remains an unused source fixture; dependency injection and runtime references were removed. Mobile URI parsing helpers exist, but no generic QR-scanning screen is exposed by the current guided enrollment UI. Documentation cards describe repository resources rather than linking to complete hosted manuals. No other page-component routes were discovered in the five application trees.

## 2. Fake, hardcoded and misleading content found

| Finding | Original classification | Correction / current evidence |
|---|---|---|
| Homepage `LIVE`, 6.23 MiB, 3.59 MiB, 42.4%, verified example | DEMO / MISLEADING | Removed illustrative output entirely; live HTML still contains LIVE and 42.4% |
| Free/Cloud Individual/Enterprise plan concepts and unimplemented features | PLACEHOLDER / MISLEADING | Replaced by no public pricing; no subscription or purchase CTA |
| Keycloak, Vault, MinIO, events/monitoring stack presented with implemented components | MISLEADING | Architecture now distinguishes current API/filesystem implementation from absent integrations |
| Passkeys, enterprise SSO and managed encryption wording | UNVERIFIED / MISLEADING | Removed available-feature framing; limitations stated explicitly |
| Admin lossless success always 100% | HARDCODED / MISLEADING | Measured verified file-record fraction; null when there are no records |
| Admin incident/quarantine counts always zero | HARDCODED / MISLEADING | API returns null; UI says Unknown/reporting not implemented |
| Jobs today counted every file | BROKEN / MISLEADING | Counts records since midnight UTC |
| Active users actually registered account count | MISLEADING | Label now Registered users; no active-session claim |
| Negative net saving clamped to zero | MISLEADING | Preserve measured original-minus-artifact difference |
| Every account labelled active; missing last login labelled Never | HARDCODED / MISLEADING | Registered / Not recorded |
| Admin health fabricated service definitions, version/latency fields | DEMO / UNVERIFIED | Reads safe public readiness endpoint; removes unmeasured metrics |
| Admin layout always Development and Administrator, even signed out | HARDCODED / MISLEADING | Runtime environment and actual local session label |
| Portal avatar MT and private-workspace claim | HARDCODED / UNVERIFIED | Removed initials; account-based processing wording |
| Angular demo login and empty-history branch | DEMO | Removed branches, even when a demo flag is accidentally enabled |
| Desktop stored history reloaded as zero sizes | BROKEN | Deserialize existing persisted field names; regression test added |
| Desktop event-count progress looked like measured completion | MISLEADING | Indeterminate progress indicators |
| Desktop checksum presence implied verified integrity | MISLEADING | UI says checksum reported/not reported |
| Desktop cloud cancel button did not cancel its request | BROKEN | Hide unsupported cloud cancel; retain local process cancellation |
| Sitemap last-modified fabricated from current request/build time | HARDCODED | Removed unsupported last-modified timestamp |
| Authenticator unlocked when device authentication was unsupported | BROKEN | Fail closed; unsupported authentication returns false; regression test added |

Maintained headings, workflow explanations, project identity and unavailable/draft notices are REAL_STATIC descriptions of source scope. Authorized API records are REAL_DYNAMIC when retrieved successfully; this does not independently verify deployment persistence or historical completeness. Local TOTP/time and file-history measurements are dynamic local sources, not backend operational statistics. Historical build reports are STALE evidence for current distribution and explicitly TEST. [suspicious-source.csv](suspicious-source.csv) preserves remaining search hits as DEMO or UNVERIFIED candidates; a keyword hit is not a new verified defect or a production claim.

## 3. Broken functions found

Fixed locally: missing singular download route; hidden mobile website navigation; hidden admin logout at small widths; public share fetch error state; desktop persisted metrics; unsupported cloud cancel; missing desktop decompression error display; stale account MFA display after failed refresh; stale selected-file download ID; error combined with a false empty history state; admin reporting and environment labels. No destructive admin action was added.

Remaining: live `/download` and admin `/privacy` return 404; no interactive live validation; Angular has no configured test target; production scanner readiness cannot be established from this audit's timed-out API probes. Full release pipeline execution cannot complete without signing/install evidence.

## 4. Missing functions found

NOT_IMPLEMENTED: billing/checkout/subscriptions/feature tiers; paid enterprise sales workflow; incident-management and quarantine-management backing models/APIs; role editing/account suspension; self-service server account deletion; retention control; full hosted product manuals; functional support contact endpoint; verified passkeys/SSO/managed envelope encryption; uptime history/incident history service. Mobile generic QR import is not a visible supported flow. These are not advertised as working capabilities after local corrections. Do not add destructive administrative APIs simply to fill a dashboard.

## 5. Public website review — PARTIAL

All discovered public page source files, shared header/footer/CTA, deployment URL configuration, robots and sitemap were inspected. Homepage sample results were removed. Footer prototype wording is retained. Contact form is visibly disabled. Terms remain an explicitly unfinished draft, not invented legal guarantees. Documentation is a resource overview with an architecture link, not a complete manual. Local responsive navigation now remains visible and wraps; keyboard focus is visible. No screenshot/visual-interaction pass is claimed.

## 6. Status review — PARTIAL

The page already used `/public/status`; no invented uptime history was found in this revision. It now normalizes all six known services, preserves unknown, exposes scanner degradation and derives an overall state that cannot override a degraded dependency with an upstream operational label. Fetch/HTTP/JSON failures show status unavailable and unknown dependency states, with reload guidance. Labels explain that identity is database connectivity and compression is prerequisite readiness. No email-delivery, end-to-end login, persistence or compression success is inferred. Historical monitoring is explicitly unavailable.

`/health` is liveness and selector-file evidence, not whole-product readiness. The known scanner-unavailable snapshot provided by the operator was not hardcoded. This audit's live API probes timed out; HTTP 200 on the public status page is not API-health proof.

## 7. Pricing review — PASS locally; FAIL deployed content

No billing endpoints, payment provider integration, subscription models or enforceable plan tiers were found in the active platform implementation. Public pricing now says unavailable; no invented free-testing business plan or future pricing promise was introduced. Deployed HTML still contains the old three plan names.

## 8. Download/release review — PARTIAL; distribution BLOCKED

| Platform | Build/signing evidence | Version/channel | Public URL/install validation | Classification |
|---|---|---|---|---|
| Android | Historical artifact report records debug signing | Source 0.1.0+1; report lacks verified package version | No approved release metadata; target-phone install not verified | TEST |
| Windows | Historical folder/ZIP report explicitly unsigned | Source 0.1.0+1; package version not independently verified | No approved release metadata; clean installation not verified | TEST |
| iOS | No distributable artifact established | No release | No hosted/signed/install-tested release | NOT_AVAILABLE |
| macOS/Linux/CLI | Source exists for some workflows; no approved binary | No production release | No verified production asset | NOT_AVAILABLE |

The public manifest contains zero artifacts. Buttons are derived from validated metadata and remain disabled when absent. Metadata supports platform/version/date/architecture/filename/size/SHA-256/signing/channel/release notes/URL. It accepts only the existing repository's version-tagged GitHub Release assets. No local paths are exposed. Metadata declarations alone do not prove a signature: publication still requires operator-owned signing and installation evidence. See [RELEASE_DISTRIBUTION.md](../RELEASE_DISTRIBUTION.md) for the concrete procedure and remaining automation gates. No test package was promoted or uploaded.

## 9. Admin .NET deep review — PARTIAL

Login posts to the real API and verifies `/admin/stats` authorization before retaining tokens in a Blazor server circuit. Protected data calls enforce server API authorization and clear sessions on 401/403. UI hiding is not relied on as authorization. Logout clears the circuit and attempts refresh-token revocation; it is not global immediate access-token revocation.

Dashboard derives from database records with corrected measurement labels. Users is read-only with client filtering; role/MFA values come from records, status now means registered and last login is not recorded. Jobs lists stored file records, not a durable queue of all failed/running attempts. False integrity flags say Not verified rather than Pending. Audit shows up to 500 stored events; IP/source data is not recorded by that model. System reads sanitized readiness and handles failures with Unknown/error/retry. Incidents and quarantine are explicitly not implemented; an empty result is not evidence of zero incidents. No delete/suspend/role-change/release-quarantine buttons or APIs were introduced. Privacy was added with a navigation link.

Limitations: no pagination for user/job tables, no authenticated browser tests, no real admin account available in this task, no dedicated .NET test project. Table overflow and mobile logout accessibility were corrected. Optional OIDC configuration is disabled and not evidence of working production SSO. Production configuration must keep disabled development placeholders from becoming active.

## 10. Privacy review — PARTIAL / BLOCKED operator decisions

Source data inventory: email, display name, password hashes, roles, timestamps, MFA enabled state, TOTP secrets/enrollment records, hashed refresh tokens; uploaded contents, original/artifact paths, filenames, sizes, checksums, codec/status/owner; recipient email, share-code hash, expiration/download counters; audit actor/action/resource/result/details/time. The API stores TOTP secrets needed for verification; no at-rest secret-encryption guarantee is asserted. Successful cloud uploads and artifacts persist in configured storage; share expiry is not deletion. Retention/deletion policy is not implemented.

Portal tokens are in localStorage. Admin tokens are server-circuit memory. Mobile factors are in secure storage; cloud tokens are in memory. Desktop settings/history include local paths; clearing local history does not delete cloud content. Email providers process recipient/message content and optional attachments. Runtime/provider access logs and IP/device metadata retention were not inspected at the hosting-provider layer. Application audit records do not establish a complete access-log policy. No analytics/cookie-consent system or certification was invented.

Public privacy now explains actual behavior with an explicit policy-draft label. Admin/mobile/desktop have data-use disclosures; portal links to the public draft and registration mentions unresolved retention. Public share lookup no longer reveals filenames, sizes or codec without recipient authorization; its page is noindex and disallowed in robots. Still required: operator identity/contact, processors/data locations, backups/log retention, legal basis/terms, deletion/support process and review. These cannot truthfully be finalized from source alone.

## 11. Security claim review — PARTIAL

Removed supported-feature framing for passkeys, OIDC/enterprise SSO and managed envelope encryption. Scanning is described as architecture with explicit fail-closed availability limits and a status link. Integrity is separated from confidentiality/malware safety. No GDPR/SOC 2/ISO/HIPAA/zero-knowledge/E2EE certification claim was introduced. Local tests exercise scanner failure handling, but operational ClamAV/YARA and real file processing remain release gates.

## 12. Login/register/navigation — PARTIAL

The portal origin is supported by the previous audit's observed live links and current source configuration: `https://portal-xai.vercel.app`; this audit also received HTTP 200 from login/register. Header CTAs use this configured origin, not `#` or a fabricated modal. `/download` redirects locally. Mobile navigation remains accessible via wrapped links. Protected share pages link to the real inbox and do not send codes as login URL parameters. [actions.csv](actions.csv) lists source action declarations; UNVERIFIED means no browser interaction proof, not PASS.

## 13. Angular review — PARTIAL

Login/register, refresh/logout, history/download, compression, decompression, shares and email actions use API services. Refresh is serialized and bounded; errors clear expired sessions. Silent demo authentication/history were removed. Dashboard reads real history and handles empty/error states. Settings exposes actual email/MFA and resets unknown on failure. Security screen directs enrollment to mobile; therefore first-time MFA availability is BLOCKED for users without the test authenticator. No public production app release exists. Compression scanner failures now say processing temporarily unavailable. Browser downloads initiate a save; the browser does not provide proof of successful disk persistence. Unit-test infrastructure is absent, not a passing empty test suite.

## 14. Mobile review — PARTIAL

Reviewed startup/loading/storage-error retry, device unlock, home/account codes, guided login/register/enrollment/email verification/storage retry/TOTP confirmation/restart/logout, local-factor deletion confirmation and clipboard action. TOTP success depends on server confirmation; secure storage failure prevents enabling before provisioning. FlutterFragmentActivity is retained. A discovered fail-open device-authentication branch was corrected: unsupported device authentication now denies unlocking. Secure storage was not weakened. No compression/download feature is claimed for this authenticator. Clipboard codes are user-triggered and short-lived; no universal clipboard erasure guarantee is made. Real phone enrollment, email receipt, lifecycle/device behavior and signed installation remain unverified.

## 15. Desktop review — PARTIAL

Reviewed cloud/local compress and decompress, settings, history, account login/register/MFA/logout, cloud history/download and share redemption. Added history serialization regression protection, removed fake progress measurement, stopped claiming checksum presence proves verification, cleared stale results at cloud start, exposed decompression errors and removed unsupported cloud cancel. Release builds show the actual fixed API URL as read-only. Local paths are legitimate desktop settings, not public download URLs. Remaining limitations include local process cancellation races/output persistence edge cases, external Python/checkpoint setup and no authenticated live desktop E2E. The live integration test remains deliberately skipped without its explicit environment flag.

## 16. Real feature matrix

| Feature / advertised location | Backend | Next.js | Angular | Mobile | Desktop | Admin | Production tested | Status |
|---|---|---|---|---|---|---|---|---|
| Password login/register | Implemented | Links | Implemented | Implemented | Implemented | Login only | HTTP entry pages only | PARTIAL |
| TOTP enrollment/login | Implemented | Described | Login/status; setup instructions | Guided enrollment/codes | Login code | Login code | No real delivery/device E2E | BLOCKED |
| Compression/decompression | Implemented, scanner-gated | Described | Implemented | Not applicable | Local/cloud | Inspection only | No current live roundtrip | BLOCKED |
| History/download | File records/artifacts | Not applicable | Implemented | Not applicable | Implemented | Read-only records | No authenticated live test | PARTIAL |
| Recipient shares | Implemented | Protected landing | Create/redeem/download | Not applicable | Redeem/download | Audit only | Not live tested | PARTIAL |
| Attachment email | Provider-dependent | Not offered | Request/error handling | Not applicable | Not offered | Configuration API only | No actual receipt | BLOCKED |
| Service readiness | Safe public endpoint | Dynamic page | Error handling | Error handling | Error handling | Dynamic page | Page HTTP only; API timeout | PARTIAL |
| Admin users/jobs/audit | Admin-authorized endpoints | Not applicable | Optional admin link | Not applicable | Not applicable | Read-only | Not authenticated live tested | PARTIAL |
| Incidents/quarantine management | Absent | Not advertised | Absent | Absent | Absent | Unavailable notices | No | NOT_IMPLEMENTED |
| Billing/enterprise plans | Absent | Unavailable notice | Absent | Absent | Absent | Absent | No | NOT_IMPLEMENTED |
| Signed public apps | No approved release | Empty validated manifest | Not applicable | Signing blocked | Unsigned build | Not applicable | No | BLOCKED |
| Privacy/deletion/retention | Data exists; deletion absent | Draft disclosure | Link/notice | Disclosure/local removal | Disclosure/local history clear | Disclosure | Operator policy not finalized | PARTIAL |
| Passkeys/SSO/envelope encryption | Not integrated in active API | Explicitly not verified | Not offered | Not offered | Not offered | Optional OIDC config only | No | NOT_IMPLEMENTED |
| Uptime/incident history | Absent | Not available | Absent | Absent | Absent | Not available | No | NOT_IMPLEMENTED |

## 17. Exact files modified

See [modified-files.txt](modified-files.txt), generated from the scoped working-tree diff plus newly created audit/test/release files. Pre-existing unrelated engine/scratch deletions were preserved. No secrets or the IDE's API-key CSV were read.

## 18. Backend endpoints added/modified and gaps

No new backend endpoint or schema migration. Modified `GET /admin/stats` (admin authorization unchanged): UTC daily count, measured net bytes, null unavailable counts and measured file verification ratio. Modified `GET /admin/users`: registered instead of invented active state. Modified `GET /public/shares/{code}`: only authentication-required availability; metadata stays behind existing recipient-authorized POST. This is an intentional public response contraction; the local Next.js consumer was updated and deployments must be coordinated.

Potential APIs, not implemented speculatively:

| Method/path | Authorization | Input | Output | Risk / why required |
|---|---|---|---|---|
| GET /admin/incidents | Admin | Bounded cursor/filter | Recorded scanner events | Sensitive detections; requires durable incident model before a management UI |
| GET /admin/quarantine | Admin | Bounded cursor/filter | Recorded retained quarantine items | Sensitive filenames; current pipeline does not establish a reviewable quarantine store |
| DELETE /auth/account | Reauthentication + MFA as applicable | Confirmed deletion request | Job/receipt with actual deletion state | Destructive; retention/backups/legal policy and full ownership cleanup must be specified first |
| PATCH /admin/users/{id}/role | Privileged admin + step-up | Reviewed role transition | Audited transition | Privilege escalation/lockout; no current product requirement justifies adding this now |

## 19. Packages added/removed

No application dependency declarations were added or removed. Public lint command was repaired with an ESLint flat config using the installed Next.js ESLint dependencies. Existing backend requirements were installed into the local virtual environment because FastAPI/pyotp/httpx and related declared dependencies were missing. This is test-environment setup, not a deployed dependency update. Release/status tests use Node built-ins.

## 20. Test results

See [validation.md](validation.md) for final command outcomes. Backend: 93 tests passed after allowing the existing YARA DLL to load outside the sandbox. Initial run: 82 passed, 11 scanner-related failures caused by DLL access denial. These are isolated/mocked logical tests, not production email/scanner proof. Mobile: analysis clean and 15 tests passed. Desktop: analysis clean, 5 tests passed, 1 explicit live test skipped. Public status/release tests: 8 passed. Other final build results are recorded separately. Android release build correctly fails when production signing variables are absent; no debug-signing bypass was applied.

## 21. Local status

PARTIAL: product truth/privacy corrections are implemented locally with targeted verification. Unimplemented capabilities are removed from available-feature claims or explicitly unavailable. Complete browser/visual/physical-device verification is BLOCKED. Remaining uncertain candidates are not silently promoted to PASS.

## 22. Deployed status

FAIL for known old misleading homepage/pricing content and missing routes. No fixes were deployed. Public share API/frontend changes need coordinated deployment. Do not assume repository edits changed Vercel or Render.

## 23. Live verified status

[live-checks.json](live-checks.json) records timestamps, HTTP status, actual links and suspicious deployed strings. Public `/download`: 404. Admin `/privacy`: 404. Public root: HTTP 200 with old LIVE/42.4% content. Pricing: HTTP 200 with old plan names. Other discovered static public pages: HTTP 200. Admin root/login/system: HTTP 200. Portal login/register: HTTP 200. Backend health/status/admin authorization probes timed out and are BLOCKED, not inferred unavailable or operational. No browser session was connected; no authenticated interaction passed in this audit.

## 24. Remaining release blockers

Deploy and verify corrected website/API/admin together; restore and prove operational ClamAV/YARA; verify production DB schema and persistence; complete real MFA enrollment/login on the actual phone with real Brevo delivery; prove critical file roundtrips and recipient downloads live; resolve attachment-provider support and receipt; supply approved signing identity and perform clean installs; finish operator privacy/contact/retention/deletion/legal decisions; complete browser/mobile-layout and authorization checks. Angular test runner and a secure automated signing/publication workflow remain incomplete. **Production readiness remains BLOCKED.**
