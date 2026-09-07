from pathlib import Path

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
sections = ["""# XAI executed runtime verification — 2026-09-07

Overall: FAIL for the requested security pipeline. Local and authenticated HTTP compression/decompression integrity passed, including after rebuilding Docker. No ClamAV or YARA scanning was performed: the actual API contains no scanner calls, the backend has no scanner binaries/module/rules, and the active Compose configuration has no scanner services to start. No scanner was disabled or bypassed during this verification. Compression PASS below describes functional execution only, not malware safety.

The previously named `second_file_test_corrected.py`, `second_file_test.py`, and `runtime_hybrid_profiles.py` and their saved stdout/stderr were not found in the inspected workspace or direct temporary-directory matches. These are fresh executed results from `scratch/runtime-validation/verify_current.py`, not recovered historical stdout. The new second input is the existing nonempty UTF-8 Markdown file `deployment/README.md`. Its selection does not establish the identity of the earlier second input.

The first input was re-compressed and decompressed too; no historical PASS was assumed. The decompressor was called with input/output paths and supported arguments only. API tests created two disposable local accounts, one before and one after rebuild. Passwords/tokens were generated in memory and were not printed or persisted. No messages or email were sent.

## Local round-trips
"""]
def log(title, name):
    sections.append('\n## '+title+'\n\n```text\n'+(out/name).read_text(encoding='utf-16').strip()+'\n```\n')
log('Fresh local output', 'local-output.txt')
log('Hybrid profiles', 'profiles-output.txt')
sections.append('''
## Port 8000 identity

Executed `netstat -ano`, PowerShell/CIM process inspection, `docker compose ps`, and in-container `/proc/1/cmdline`/module inspection. Initial sandbox access denial was resolved by an authorized escalated read; the commands succeeded.

```text
PORT_8000_PID=10716
PROCESS_NAME=com.docker.backend.exe
PROCESS_COMMAND_LINE="C:\\Program Files\\Docker\\Docker\\resources\\com.docker.backend.exe" services
IPV6_LOOPBACK_PID=3888
IPV6_LOOPBACK_PROCESS_NAME=wslrelay.exe
IPV6_LOOPBACK_PROCESS_COMMAND_LINE= --mode 1 --vm-id {bea3260a-a103-4251-a7d5-f8d799edd02b} --handle 2268
DOCKER_SERVICE=backend
DOCKER_CONTAINER=xai-backend-1
CONTAINER_PROCESS_COMMAND_LINE=/usr/local/bin/python3.12 /usr/local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
APP_MODULE=/app/app/main.py
APP_SHA256=58c35c838515b10b47e3b4e3eb4dcd09325b536dd21b04e448cc6b3d6e8c348f
HOST_SERVICES_API_FASTAPI_APP_MAIN_SHA256=58c35c838515b10b47e3b4e3eb4dcd09325b536dd21b04e448cc6b3d6e8c348f
FASTAPI_IDENTITY=PASS
```

Port 8000 forwards to the intended Dockerized FastAPI app; its loaded source hash matches `services/api_fastapi/app/main.py`. A second service on another port was unnecessary.
''')
log('Raw HTTP responses and authenticated API round-trip before rebuild', 'api-output.txt')
log('Actual relevant route decorators', 'routes-output.txt')
sections.append('Compression is synchronous. Its response provides `job_id` and `status`; `/history` lists owned file/job records. There is no dedicated per-job polling route and no included router in this module.\n')
sections.append('''
## Security gate

```text
CLAMAV_STATUS=FAIL: unavailable; no clamscan or clamdscan in backend; no API integration
CLAMAV_SCAN_RESULT=NOT EXECUTED
YARA_RULES_PATH=NONE: no .yar or .yara files under /app or /opt/xai-compress
YARA_SCAN_RESULT=NOT EXECUTED: Python yara module absent; no API integration
SCANNER_COMPOSE_SERVICES=NONE
SECURITY_PIPELINE=FAIL
```

The actual `compress_upload` calls the engine and verifies a decompressed hash. `decompress_upload` validates the container, decompresses and hashes the restored bytes. Neither calls ClamAV or YARA before compression or after decompression. Source searches in API/services, infrastructure, deployment and scripts found no scanner integration. `docker compose config --services` returned db, backend, admin, angular, nextjs. There are no existing Docker scanner services to start and retry. Adding a scanner stack and API enforcement is outstanding work, not an executed success.

## Path robustness correction

Before the correction, starting the same Python from `services/api_fastapi` printed `SELECTOR_EXISTS=False`, while root printed True; hybrid profiles loaded in both. Added `Settings.resolve_runtime_paths` in `services/api_fastapi/app/config.py`: relative selector paths resolve against the repository derived from `__file__` with pathlib; configured absolute paths remain absolute. No user-specific path is hardcoded. Both following runs actually load the selector artifact and balanced profile after the fix.
''')
log('Repository working directory', 'root-path-output.txt')
log('API working directory', 'api-path-output.txt')
sections.append('''
```text
ROOT_CWD_TEST=PASS
API_CWD_TEST=PASS
```

## Docker execution and runtime assets

Executed `docker compose build backend` (exit 0), `docker compose up -d backend` (exit 0), and `docker compose ps`. Backend was recreated; db/storage volumes retained. Final state: `xai-backend-1`, Up (healthy), host 8000 -> container 8000. Existing Dockerfile copies the Python package, selector checkpoint and configs; those COPY instructions were verified during the build.

```text
DOCKER_BUILD=PASS
DOCKER_IMAGE_MANIFEST=sha256:83ea191b48e79621939ab86b9473fad4fe0a3437286f8c5c4e027e2b2aa8c743
DOCKER_CONTAINER_STATUS=running (healthy)
PACKAGE=/opt/xai-compress/xai_compress/__init__.py
SELECTOR_PATH=/opt/xai-compress/checkpoints/selector_v2/best.json
SELECTOR_LOADED=True
SELECTOR_ERROR=None
HYBRID_PROFILES_PATH=/opt/xai-compress/configs/hybrid_profiles.json
CONFIG_ASSETS=/opt/xai-compress/configs/model_search_v2.json; /opt/xai-compress/configs/gru_default.json; /opt/xai-compress/configs/hybrid_profiles.json; /opt/xai-compress/configs/default.json
DOCKER_HEALTH_STATUS=200
DOCKER_PUBLIC_STATUS=200
DOCKER_COMPRESSION=PASS (HTTP 200)
DOCKER_DECOMPRESSION=PASS (HTTP 200)
```

Inside the rebuilt container, selector artifact loading and all three profile loads succeeded. Both raw HTTP bodies below were also independently retrieved inside the container using urllib; both internal requests returned 200. No GRU/transformer checkpoint loading was exercised or claimed. The authenticated repeat below used the rebuilt container's published port, with actual upload, artifact download and restored-response byte comparison.
''')
log('Rebuilt Docker authenticated round-trip and raw status', 'docker-output.txt')
sections.append('''
## Final statuses

```text
SELECTOR LOADED: PASS
HYBRID PROFILES LOADED: PASS
LOCAL ROUND-TRIP #1: PASS
LOCAL ROUND-TRIP #2: PASS
LOCAL SHA256 INTEGRITY: PASS
FASTAPI IDENTITY: PASS
FASTAPI COMPRESSION: PASS
FASTAPI DECOMPRESSION: PASS
FASTAPI SHA256 INTEGRITY: PASS
CLAMAV: FAIL
YARA: FAIL
SECURITY PIPELINE: FAIL
PATH ROBUSTNESS: PASS
DOCKER BUILD: PASS
DOCKER COMPRESSION: PASS
DOCKER DECOMPRESSION: PASS
DOCKER SHA256 INTEGRITY: PASS
PUBLIC STATUS COMPRESSION: operational
```

`/public/status` reports compression assets as operational, but does not probe scanners or demonstrate malware safety. Overall public status is degraded because notifications are degraded. No browser, email delivery, external deployment, or malware scan was executed in this verification.
''')
(root/'docs/XAI_E2E_REPORT.md').write_text('\n'.join(sections), encoding='utf-8')
print('REPORT_PATH='+str(root/'docs/XAI_E2E_REPORT.md'))
