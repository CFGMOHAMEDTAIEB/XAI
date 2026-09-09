# Render scanner recovery and remaining client checks

This runbook prepares the remaining work. It does not provision a Render service,
assume an internal hostname, or change the live backend environment.

## Evidence before deployment

The backend defaults to CLAMAV_HOST=clamav, CLAMAV_PORT=3310 and required scanning.
In production it defaults to /app/security/yara/production. Before this change the
production directory had no YARA rules. The local ignored Render API environment
file set APP_ENV=production but had no scanner overrides. Provider settings may
differ: inspect them before concluding that Render uses the same defaults.

/public/status returns only aggregate scanner health; /health checks the API/model,
not scanner readiness. An HTTP 200 /health does not prove compression is usable.
The existing security_scan application logs contain per-stage clamav_status,
yara_status, error, allowed, request_id, sha256 and timestamp. Read only these
scanner records; do not export unrelated environment values or credentials.

After the updated image is available, run inside the FastAPI service at /app:

```sh
python security/diagnose_scanners.py
```

This read-only script prints an allowlist of scanner configuration, DNS/PONG
results, ruleset hashes/count and scanner health. It never dumps Settings or the
whole environment. Before redeploying, the same checks can be performed from
Render Shell using the existing app.config and app.security_scanner modules.

## ClamAV service topology

1. Inspect the actual backend workspace, region, plan and network-isolation settings.
   Locate an existing ClamAV private service before creating anything.
2. If none exists, prepare a Render **Private Service**, using the repository root
   build context and services/api_fastapi/security/clamav/Dockerfile. A background
   worker cannot receive the daemon connection. Do not create a public web service
   for ClamAV and do not expose port 3310 publicly.
3. Use the same workspace/region as FastAPI and permit private backend-to-daemon
   connectivity. Size memory for signature reloads: ClamAV documents 3 GiB minimum,
   4 GiB preferred. Verify the actual paid instance and disk costs/account support
   before provisioning; these have not been inspected in this session.
4. Keep the existing official image entrypoint, FreshClam updates, health probe and
   AlertExceedsMax policy. Persist signatures at /var/lib/clamav where supported;
   confirm disk ownership and update access. Do not disable updates, scanning, or
   exceeded-limit detection to fit an undersized instance.
5. Wait for signatures to load and clamdcheck.sh to succeed. Inspect logs for memory
   pressure, failed updates or restarts. Confirm Render's own service readiness;
   do not assume Docker HEALTHCHECK alone is sufficient on the provider.
6. Copy the real internal hostname from **Connect > Internal** / Service Address.
   CLAMAV_HOST takes the host only (no scheme or :3310). No hostname is guessed in
   this repository. The example file deliberately uses an unresolved placeholder.

Only after actual discovery, set the existing FastAPI variables:

| Variable | Required value |
| --- | --- |
| APP_ENV | production |
| SECURITY_SCAN_REQUIRED | true |
| CLAMAV_HOST | Actual private hostname copied from Render |
| CLAMAV_PORT | 3310 |
| YARA_RULES_PATH | /app/security/yara/production |

Deploy the reviewed production rules with the existing backend Dockerfile; it
already copies services/api_fastapi/security into /app/security. Restart/redeploy
because compiled rules are cached. Do not point production at the test directory.
No database, JWT, email or frontend variables need to change for this repair.

The included baseline has two PHP request-execution detections and one private
helper. See the rules README for review scope, false positives and coverage gaps.
This is a minimal defensive baseline, not complete malware coverage.

## Production acceptance gate

Check /health and /public/status, then inspect per-scanner diagnostics and logs.
Require both ClamAV and YARA operational. Run a small authenticated synchronous
/compression/jobs upload, download /files/{id}/download, POST the artifact to
/compression/decompress, and compare original/restored SHA256. Record byte counts,
job ID, ratio, HTTP statuses and both upload/output scanner log records.
A successful response alone must not be described as separate observed scanner
log evidence. Do not invent a polling route. Never run the unavailable-scanner
fault injection on the live service: it is covered in isolated local tests.

## Android signing and phone failure

The existing signing mechanism already supports XAI_ANDROID_KEYSTORE,
XAI_ANDROID_STORE_PASSWORD, XAI_ANDROID_KEY_ALIAS and XAI_ANDROID_KEY_PASSWORD.
Use operator-owned material via that mechanism after production E2E passes.
Keystore files/key.properties are already ignored in the Android directory;
prefer protected storage outside the repository, and never put secrets in a command
history, source file or report. No key has been generated by this work.

Once a phone is connected and authorized, use its actual adb serial:

```powershell
adb devices
adb -s SERIAL logcat -c
adb -s SERIAL shell am force-stop com.example.xai_compress_authenticator
adb -s SERIAL shell am start -W -n com.example.xai_compress_authenticator/.MainActivity
adb -s SERIAL logcat -d
adb -s SERIAL shell pidof com.example.xai_compress_authenticator
```

SERIAL is a documentation placeholder, not an invented device identifier. Store
raw device logs locally in ignored dist/ output and redact secrets before sharing.
Use the actual crash stack before editing startup code. No phone is connected at
present, so the startup root cause is unknown. Do not classify the FlutterActivity
or biometric code as the crash cause without a stack trace.

After a proven fix, run existing Flutter checks and rebuild through
scripts/build_production.ps1 without -AllowDebugSigning for a production-signed
artifact. Verify with apksigner verify --print-certs, then clean-device install,
launch, sustained process lifetime and HTTPS API traffic. The current mobile UI
has no backend login call site; adapter tests alone do not prove packaged UI auth.

## Windows

The existing artifact is an unsigned ZIP of the EXE, DLLs and data. Use a genuine
operator-supplied code-signing certificate or signing service; none is provisioned
by this work. There is no existing Windows signing command in the build script.
Do not invent one or claim unsigned packaging is signed. Label current distribution
TEST ONLY. A clean x64 PC must have the compatible Visual C++ runtime (MSVCP140,
VCRUNTIME140 and VCRUNTIME140_1) and the whole extracted release folder. Local engine
modes additionally need the separately configured Python engine/checkpoint.

References: [Render private services](https://render.com/docs/private-services),
[Render private network](https://render.com/docs/private-network),
[ClamAV Docker requirements](https://docs.clamav.net/manual/Installing/Docker.html).
