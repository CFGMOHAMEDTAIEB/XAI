# Remaining production blockers — 2026-09-08

## Outcome

Both existing client artifacts remain **TEST ONLY**. No Render service, live
environment variable, mobile/desktop executable, signing credential, TLS/auth
behavior, compression algorithm, API contract or fail-closed policy was changed.

| Check | Result and evidence |
| --- | --- |
| PRODUCTION CLAMAV | BLOCKED: no authenticated Render access; individual daemon state/hostname unknown |
| PRODUCTION YARA | BLOCKED: new rules validated locally, not deployed to Render |
| SCANNER HEALTH | FAIL: current /public/status returns security_scanner unavailable |
| PRODUCTION COMPRESSION | BLOCKED: fresh authenticated POST /compression/jobs returns HTTP 503 |
| PRODUCTION SHA256 | BLOCKED/not measured: no production artifact/restored output; not a hash mismatch |
| ANDROID RELEASE BUILD | PASS from previous build; current artifact hash reverified |
| ANDROID SIGNING | BLOCKED: unchanged Android Debug certificate |
| ANDROID REAL INSTALL | BLOCKED: user reports installation, no connected phone for command verification |
| ANDROID REAL STARTUP | BLOCKED: user reports failure; no device/stack trace available |
| ANDROID BACKEND CONNECT | BLOCKED on real phone; prior live API-adapter test passed |
| WINDOWS RELEASE BUILD | PASS from previous build; current ZIP hash reverified |
| WINDOWS SIGNING | BLOCKED: unchanged unsigned distribution |
| WINDOWS CLEAN-PC TEST | BLOCKED: no clean Windows environment supplied |
| WINDOWS BACKEND CONNECT | PASS from prior actual release UI sign-in; artifact unchanged |

## Diagnosis before changes

Fresh GET /health: HTTP 200, status ok, selector_v2 true.
Fresh GET /public/status: HTTP 200, status degraded, security_scanner unavailable.
Fresh auth flow: register/login/auth-me/history all HTTP 200; upload HTTP 503,
`File security verification unavailable; retry later`. Both refresh tokens revoked.
See production-api-check.txt. A synthetic example.com account was created; no
credentials/tokens were persisted in this report or source.

The exact application cause is enforce_scan refusing to release bytes when the
combined ScanResult.clean is false. scan_file requires both ClamAV and YARA clean.
/public/status exposes only combined readiness, so it cannot identify the failing
component, DNS failure, OOM/reload/startup state or invalid runtime path.

Repository evidence before editing:
- production YARA contained no .yar/.yara files, intentionally. load_yara_rules
  rejects an empty directory with ValueError('No YARA rules configured').
- Settings defaults CLAMAV_HOST=clamav, CLAMAV_PORT=3310 and required scanning.
- APP_ENV=production selects /app/security/yara/production in the Docker image.
- Dockerfile copies security/ to /app/security and installs yara-python 4.5.4.
- The ignored local deployment/.env.render.api had APP_ENV=production and no
  CLAMAV_HOST/CLAMAV_PORT/SECURITY_SCAN_REQUIRED/YARA_RULES_PATH assignments.
- This local file is not proof of provider settings. The actual Render topology,
  environment, logs, internal hostname, account/plan and same-region connection
  remain uninspected. No Render connector/CLI was available, and supported browser
  discovery returned no available browsers. Connection was requested from the user.

Conclusion: empty production rules are a proven repository blocker; a Compose
hostname is also an unsafe Render template default. It is not yet possible to
claim either or both are the exact currently deployed failure without Render logs.

## Changes and validation

Production rules path: services/api_fastapi/security/yara/production, copied to
/app/security/yara/production by the existing image. One rule file contains **two
PHP request-execution detections plus one private helper**. No synthetic test
marker in production logic. Narrow behavior signatures reviewed for their scope;
not externally certified and not comprehensive malware coverage. The README
explicitly records false-positive cases and evasion limitations.

53 tests passed in an isolated disposable backend container with networking off:
real YARA compilation, inert positive examples, clean text/JSON/CSV/PHP/XAIC data,
project files, synthetic-rule rejection, empty/invalid/duplicate rule failures,
scanner-unavailable HTTP 503, and existing scanner/hardening regression checks.
The first run passed 52 and failed one because /app selected the old image source;
rerunning with /repo/services/api_fastapi as cwd passed all 53. No policy was
weakened to resolve that test harness issue.

Real LOCAL scanner checks (not Render):
- Existing xai-clamav-1 healthy, clamdcheck.sh reports Clamd is up.
- Actual network xai_scanner-network; Docker reports 3310/tcp has no published port.
- Read-only repo mounted into a disposable container; existing backend unchanged.
- Both scanner components operational. Zero matches on README.md, selector model,
  previously generated clean.xaic and restored.md project fixtures.
- Local round-trip: 4736 original bytes -> 143 XAIC bytes -> 4736 restored bytes.
  Artifact/original ratio 0.0301943 (about 96.98% smaller).
- Original/restored SHA256:
  2eb4074d3c1115a7cedd2ac0a0439f55999b30e26051a54cb53879055fcf5c24
- ClamAV upload clean, YARA upload clean, ClamAV output clean, YARA output clean.
- Isolated process-only scanner connection failure returned HTTP 503. Restoring
  that local function returned health to operational. No production disruption.
- Evidence: local-scanner-results.json, local-scan-events.log, local-diagnostic.json.

Read-only diagnostic helper prints only scanner configuration/DNS/PONG/ruleset
counts/hashes. It does not add an endpoint, dump secrets, or change runtime settings.
Validated against the local daemon; diagnostic correctly labels its local APP_ENV
as development while loading the production rule directory.

## Render changes

**None applied. No live environment variables changed.**

Prepared deployment/SCANNER_RECOVERY.md with the actual existing Dockerfile,
private-service architecture, same-workspace/region requirement, documented
ClamAV memory needs, readiness checks and operator discovery steps. No service
hostname, provider plan or CLI flag was fabricated. No chargeable service created.

Only deployment/.env.render.api.example changed:
CLAMAV_HOST=clamav -> CLAMAV_HOST=REPLACE_WITH_RENDER_PRIVATE_HOST.
This is an explicitly non-deployable placeholder until the real host is copied
from Render Connect > Internal. APP_ENV=production, CLAMAV_PORT=3310,
SECURITY_SCAN_REQUIRED=true and YARA_RULES_PATH=/app/security/yara/production remain.
No actual .env file was modified. Rebuild/redeploy is needed to include rules;
compiled YARA is cached per backend process.

## Android and Windows

adb devices returned an empty device list. No logcat clear, force-stop, reinstall,
startup code edit or crash claim was made against a nonexistent device. The real
phone's crash root cause is UNKNOWN until its stack trace can be captured. A
FlutterActivity/biometric incompatibility must not be assumed to explain startup.
The current mobile UI also has no backend login call site; adapter evidence is
separate from real installed-app evidence.

Production compression has not passed, so the requested signing/rebuild gate has
not been crossed. Existing Android signing env support and keystore ignores are
already present. The runbook documents secure operator provisioning through that
mechanism. No signing material supplied, generated or fabricated. No rebuilt APK
was produced in this turn. No Windows certificate was supplied/used.

Unchanged Android artifact:
- Path: E:\GradleCache\xai-mobile-build\app\outputs\flutter-apk\app-release.apk
- Workspace alias: apps/mobile_authenticator_flutter/build/app/outputs/flutter-apk/app-release.apk
- Bytes: 66,651,161
- APK SHA256: 225D2E1881D43E61868ACD1B7231E2C837D34548B1685B2F900F0F773D7D9EE3
- Verified previous certificate: C=US, O=Android, CN=Android Debug
- Certificate SHA256: 9ca6174321e68cefcc04294269b6777c90c2707185fde805fb17596dbd3cc5db
- Package: com.example.xai_compress_authenticator; versionName 0.1.0; versionCode 1.
- Classification: TEST ONLY. User reports it did not open on their phone.

Unchanged Windows artifact:
- Path: E:\GradleCache\xai-desktop-build\xai-windows-20260908-155201.zip
- Bytes: 12,258,005
- SHA256: D36433ABD21FD7DCDEA46DAA7CF10D763EB48CB5F049A8194C01158912A8DC95
- Signing: unsigned EXE/DLL/data ZIP; no signed installer.
- Classification: TEST ONLY. Prior actual release startup/cloud login succeeded on
  this developer PC; no clean second-PC test. Visual C++ runtime prerequisite remains.

## Files changed this turn

- deployment/.env.render.api.example
- deployment/SECURITY_HARDENING.md
- deployment/SCANNER_RECOVERY.md (new)
- services/api_fastapi/security/diagnose_scanners.py (new)
- services/api_fastapi/security/yara/production/php_request_execution.yar (new)
- services/api_fastapi/security/yara/production/README.md
- services/api_fastapi/tests/test_production_yara.py (new)
- services/api_fastapi/tests/test_hardening.py
- scratch/production-blockers/ evidence and local validation helper (new)

Prior client modifications and unrelated working-tree changes were preserved.

## Commands

```powershell
& 'C:\Users\ss\AppData\Local\Android\sdk\platform-tools\adb.exe' devices
# Health probes used Invoke-WebRequest -UseBasicParsing, -TimeoutSec 60:
# https://xai-1-be9s.onrender.com/health
# https://xai-1-be9s.onrender.com/public/status
python scratch/production-client-validation/check_backend.py | Tee-Object -FilePath scratch/production-blockers/production-api-check.txt

# Existing venv has yara but lacks backend dependencies. pytest was installed
# there from the declared requirements; actual full tests use the backend image.
.\.venv\Scripts\python.exe -m pip install 'pytest>=8.0'

docker ps --format '{{.Names}} {{.Image}} {{.Status}}'
docker inspect --format '{{range $name, $network := .NetworkSettings.Networks}}{{$name}}{{end}}' xai-clamav-1
docker inspect --format '{{json .NetworkSettings.Ports}}' xai-clamav-1
docker exec xai-clamav-1 clamdcheck.sh

docker run --rm --network none --mount 'type=bind,source=C:\Users\ss\Desktop\XAI\XAI,target=/repo,readonly' --workdir /repo/services/api_fastapi --env PYTHONPATH=/repo/services/api_fastapi:/opt/xai-compress --env DATABASE_URL=sqlite:///:memory: --env STORAGE_PATH=/tmp/xai-test-storage xai-backend python -m pytest tests/test_production_yara.py tests/test_security_scanner.py tests/test_hardening.py -q -p no:cacheprovider --basetemp=/tmp/xai-scanner-tests

docker run --rm --network xai_scanner-network --mount 'type=bind,source=C:\Users\ss\Desktop\XAI\XAI,target=/repo,readonly' --workdir /repo/services/api_fastapi --env PYTHONPATH=/repo/services/api_fastapi:/opt/xai-compress --env DATABASE_URL=sqlite:///:memory: --env STORAGE_PATH=/tmp/xai-clean-scans xai-backend python /repo/scratch/production-blockers/check_local_scanners.py 2> scratch/production-blockers/local-scan-events.log | Tee-Object -FilePath scratch/production-blockers/local-scanner-results.json

docker run --rm --network xai_scanner-network --mount 'type=bind,source=C:\Users\ss\Desktop\XAI\XAI,target=/repo,readonly' --workdir /repo/services/api_fastapi --env PYTHONPATH=/repo/services/api_fastapi:/opt/xai-compress --env DATABASE_URL=sqlite:///:memory: --env STORAGE_PATH=/tmp/xai-diagnostic --env YARA_RULES_PATH=/repo/services/api_fastapi/security/yara/production xai-backend python security/diagnose_scanners.py | Tee-Object -FilePath scratch/production-blockers/local-diagnostic.json

Get-FileHash 'E:\GradleCache\xai-mobile-build\app\outputs\flutter-apk\app-release.apk','E:\GradleCache\xai-desktop-build\xai-windows-20260908-155201.zip' -Algorithm SHA256
git diff --check -- services/api_fastapi deployment
```

## Required to resume

Connect a supported browser signed into Render (or provide a supported authenticated
Render connection); connect/authorize the affected real Android phone; supply only
the location/reference of legitimate signing material through secure operator
configuration. Do not paste keys/passwords. A clean Windows x64 environment is also
needed for the final portability gate. No further permissions were requested for
routine local work and no automatic approval rejection occurred.
