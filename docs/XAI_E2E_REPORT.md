# XAI executed runtime verification — 2026-09-07

**Current result (2026-09-08): security integration validated.** See the appended “Executed security integration” section for real ClamAV/YARA, fail-closed, API and test evidence. The September 7 findings below are preserved historical results.

Overall: FAIL for the requested security pipeline. Local and authenticated HTTP compression/decompression integrity passed, including after rebuilding Docker. No ClamAV or YARA scanning was performed: the actual API contains no scanner calls, the backend has no scanner binaries/module/rules, and the active Compose configuration has no scanner services to start. No scanner was disabled or bypassed during this verification. Compression PASS below describes functional execution only, not malware safety.

The previously named `second_file_test_corrected.py`, `second_file_test.py`, and `runtime_hybrid_profiles.py` and their saved stdout/stderr were not found in the inspected workspace or direct temporary-directory matches. These are fresh executed results from `scratch/runtime-validation/verify_current.py`, not recovered historical stdout. The new second input is the existing nonempty UTF-8 Markdown file `deployment/README.md`. Its selection does not establish the identity of the earlier second input.

The first input was re-compressed and decompressed too; no historical PASS was assumed. The decompressor was called with input/output paths and supported arguments only. API tests created two disposable local accounts, one before and one after rebuild. Passwords/tokens were generated in memory and were not printed or persisted. No messages or email were sent.

## Local round-trips


## Fresh local output

```text
TEST=FIRST
ORIGINAL_PATH=C:\Users\ss\Desktop\XAI\XAI\README.md
ORIGINAL_BYTES=3182
FILE_TYPE=UTF-8 Markdown text
COMPRESSION_SECONDS=0.491207
DECOMPRESSION_SECONDS=0.021321
XAIC_PATH=C:\Users\ss\Desktop\XAI\XAI\scratch\runtime-validation\first.xaic
XAIC_BYTES=1683
RESTORED_PATH=C:\Users\ss\Desktop\XAI\XAI\scratch\runtime-validation\first_restored.md
RESTORED_BYTES=3182
SHA256_ORIGINAL=7b9d7503264d2ec96bf2bb92d58e39913ec675f1f7ba209793484c4064c6a6c6
SHA256_RESTORED=7b9d7503264d2ec96bf2bb92d58e39913ec675f1f7ba209793484c4064c6a6c6
HASH_EQUAL=True
TEST=SECOND
ORIGINAL_PATH=C:\Users\ss\Desktop\XAI\XAI\deployment\README.md
ORIGINAL_BYTES=14649
FILE_TYPE=UTF-8 Markdown text
COMPRESSION_SECONDS=0.253650
DECOMPRESSION_SECONDS=0.034059
XAIC_PATH=C:\Users\ss\Desktop\XAI\XAI\scratch\runtime-validation\second.xaic
XAIC_BYTES=6065
RESTORED_PATH=C:\Users\ss\Desktop\XAI\XAI\scratch\runtime-validation\second_restored.md
RESTORED_BYTES=14649
SHA256_ORIGINAL=2aeac16b1ec1cd6d3c273fd353d2acfe97ed326108e337e6151e9d8245854939
SHA256_RESTORED=2aeac16b1ec1cd6d3c273fd353d2acfe97ed326108e337e6151e9d8245854939
HASH_EQUAL=True
```


## Hybrid profiles

```text
HYBRID_PROFILES_PATH=C:\Users\ss\Desktop\XAI\XAI\engines\XAI-Compress\configs\hybrid_profiles.json
PROFILE_KEYS=["smallest", "fastest", "balanced"]
BALANCED_PROFILE={"size": 0.45, "compression_time": 0.3, "decompression_time": 0.2, "memory": 0.05}
PROFILE_LOADER=xai_compress.hybrid.profiles.load_profiles
```


## Port 8000 identity

Executed `netstat -ano`, PowerShell/CIM process inspection, `docker compose ps`, and in-container `/proc/1/cmdline`/module inspection. Initial sandbox access denial was resolved by an authorized escalated read; the commands succeeded.

```text
PORT_8000_PID=10716
PROCESS_NAME=com.docker.backend.exe
PROCESS_COMMAND_LINE="C:\Program Files\Docker\Docker\resources\com.docker.backend.exe" services
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


## Raw HTTP responses and authenticated API round-trip before rebuild

```text
HEALTH_HTTP_STATUS=200
HEALTH_BODY={"status":"ok","service":"xai-platform-api","compression":{"mode":"hybrid-v2","runtime_generation":"v3","routing":"top3","selector_v2":true}}
PUBLIC_STATUS_HTTP_STATUS=200
PUBLIC_STATUS_BODY={"status":"degraded","services":{"api":"operational","identity":"operational","compression":"operational","storage":"operational","notifications":"degraded"}}
REGISTER_STATUS=200
AUTH_ENDPOINT=http://127.0.0.1:8000/auth/login
AUTH_STATUS=200
COMPRESSION_ENDPOINT=http://127.0.0.1:8000/compression/jobs
COMPRESSION_STATUS=200
JOB_ID=9e487fce44c8254ea002756b
JOB_STATUS=completed
ARTIFACT_ENDPOINT=http://127.0.0.1:8000/files/3/download
ARTIFACT_STATUS=200
ARTIFACT_BYTES=6065
DECOMPRESSION_ENDPOINT=http://127.0.0.1:8000/compression/decompress
DECOMPRESSION_STATUS=200
SHA256_API_ORIGINAL=2aeac16b1ec1cd6d3c273fd353d2acfe97ed326108e337e6151e9d8245854939
SHA256_API_RESTORED=2aeac16b1ec1cd6d3c273fd353d2acfe97ed326108e337e6151e9d8245854939
API_HASH_EQUAL=True
```


## Actual relevant route decorators

```text
POST /auth/register -> register
POST /auth/login -> login
POST /compression/jobs -> compress_upload
GET /files/{file_id}/download -> download_artifact
POST /compression/decompress -> decompress_upload
GET /history -> history
```

Compression is synchronous. Its response provides `job_id` and `status`; `/history` lists owned file/job records. There is no dedicated per-job polling route and no included router in this module.


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


## Repository working directory

```text
PYTHON=C:\Python314\python.exe
CWD=C:\Users\ss\Desktop\XAI\XAI
SELECTOR_PATH=C:\Users\ss\Desktop\XAI\XAI\engines\XAI-Compress\checkpoints\selector_v2\best.json
SELECTOR_LOADED=True
SELECTOR_ERROR=None
CWD_TEST=PASS
```


## API working directory

```text
PYTHON=C:\Python314\python.exe
CWD=C:\Users\ss\Desktop\XAI\XAI\services\api_fastapi
SELECTOR_PATH=C:\Users\ss\Desktop\XAI\XAI\engines\XAI-Compress\checkpoints\selector_v2\best.json
SELECTOR_LOADED=True
SELECTOR_ERROR=None
CWD_TEST=PASS
```


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


## Rebuilt Docker authenticated round-trip and raw status

```text
HEALTH_HTTP_STATUS=200
HEALTH_BODY={"status":"ok","service":"xai-platform-api","compression":{"mode":"hybrid-v2","runtime_generation":"v3","routing":"top3","selector_v2":true}}
PUBLIC_STATUS_HTTP_STATUS=200
PUBLIC_STATUS_BODY={"status":"degraded","services":{"api":"operational","identity":"operational","compression":"operational","storage":"operational","notifications":"degraded"}}
REGISTER_STATUS=200
AUTH_ENDPOINT=http://127.0.0.1:8000/auth/login
AUTH_STATUS=200
COMPRESSION_ENDPOINT=http://127.0.0.1:8000/compression/jobs
COMPRESSION_STATUS=200
JOB_ID=bf57fb6353e1ed6adfd3c492
JOB_STATUS=completed
ARTIFACT_ENDPOINT=http://127.0.0.1:8000/files/4/download
ARTIFACT_STATUS=200
ARTIFACT_BYTES=6065
DECOMPRESSION_ENDPOINT=http://127.0.0.1:8000/compression/decompress
DECOMPRESSION_STATUS=200
SHA256_DOCKER_ORIGINAL=2aeac16b1ec1cd6d3c273fd353d2acfe97ed326108e337e6151e9d8245854939
SHA256_DOCKER_RESTORED=2aeac16b1ec1cd6d3c273fd353d2acfe97ed326108e337e6151e9d8245854939
DOCKER_HASH_EQUAL=True
```


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


---

# Executed security integration — 2026-09-08 Europe/Paris

This section supersedes the earlier security FAIL statuses. Earlier compression evidence and hashes above are preserved unchanged. Container timestamps below are UTC on September 7; the local date is September 8.

## Changes and actual readiness diagnosis

Added the internal scan abstraction, upload and restored-output enforcement, structured scan logs, sanitized public readiness, authenticated admin component health, YARA dependency/rules, and internal ClamAV Compose service. Compression algorithms and model artifacts were not modified. No public scan endpoint or ClamAV host port was added. The bundled YARA rule is a harmless synthetic test rule, not a comprehensive malware rule set.

Initial `docker compose ps`, `docker compose logs --tail=200 clamav`, and `docker inspect xai-clamav-1 --format '{{json .State.Health}}'` failed because the Docker Desktop Linux engine pipe did not exist. Starting Docker Desktop restored access. Actual logs showed signature update and clamd initialization, then successful health checks. Earlier runner resource constraints were not proven as the cause; no resource-cause claim is made. The healthcheck was correct and was not weakened.

The official image's default AlertExceedsMax was disabled. A small Dockerfile based on the official ClamAV image now enables it. Runtime logs confirm heuristic alerting for scans that exceed limits. FreshClam, daemon entrypoint, signature persistence and real daemon health probe remain enabled. Both required images built successfully; `docker compose up -d backend clamav` and subsequent backend recreation succeeded. Final backend and ClamAV states are healthy.

```text
CLAMAV_CONTAINER=xai-clamav-1
CLAMAV_CONTAINER_STATE=running
CLAMAV_HEALTH=healthy
CLAMD_PROCESS_RUNNING=True (PID 19 after restoration)
CLAMD_PING_RESULT=PONG
SIGNATURE_DATABASE_STATUS=daily.cld version 28116 (355647 signatures); main.cvd version 63 (3287027 signatures); bytecode.cvd version 339 (80 signatures), reported up-to-date by FreshClam
CLAMAV_HEALTH_AFTER_RESTORE=healthy
```

## Final raw health and daemon logs


CLAMAV_HEALTH_LOG=
```json
{
  "Status": "healthy",
  "FailingStreak": 0,
  "Log": [
    {
      "Start": "2026-09-07T22:11:56.812487317Z",
      "End": "2026-09-07T22:11:56.937332908Z",
      "ExitCode": 0,
      "Output": "Clamd is up\n"
    },
    {
      "Start": "2026-09-07T22:12:06.936728248Z",
      "End": "2026-09-07T22:12:07.116575813Z",
      "ExitCode": 0,
      "Output": "Clamd is up\n"
    },
    {
      "Start": "2026-09-07T22:12:17.118413686Z",
      "End": "2026-09-07T22:12:17.317632562Z",
      "ExitCode": 0,
      "Output": "Clamd is up\n"
    },
    {
      "Start": "2026-09-07T22:12:27.31980839Z",
      "End": "2026-09-07T22:12:27.517477318Z",
      "ExitCode": 0,
      "Output": "Clamd is up\n"
    },
    {
      "Start": "2026-09-07T22:12:37.514190067Z",
      "End": "2026-09-07T22:12:37.704251639Z",
      "ExitCode": 0,
      "Output": "Clamd is up\n"
    }
  ]
}
```


CLAMAV_RECENT_LOGS=
```text
clamav-1  | Mon Sep  7 22:07:21 2026 -> Set stacksize to 1048576
clamav-1  | socket found, clamd started.
clamav-1  | Starting Freshclamd
clamav-1  | Starting ClamAV
clamav-1  |
Socket for clamd not found yet, retrying (0/1800) ...ClamAV update process started at Mon Sep  7 22:10:03 2026
clamav-1  | daily.cld database is up-to-date (version: 28116, sigs: 355647, f-level: 90, builder: svc.clamav-publisher)
clamav-1  | main.cvd database is up-to-date (version: 63, sigs: 3287027, f-level: 90, builder: tomjudge)
clamav-1  | bytecode.cvd database is up-to-date (version: 339, sigs: 80, f-level: 90, builder: nrandolp)
clamav-1  |
Socket for clamd not found yet, retrying (1/1800) ...
Socket for clamd not found yet, retrying (2/1800) ...
Socket for clamd not found yet, retrying (3/1800) ...
Socket for clamd not found yet, retrying (4/1800) ...
Socket for clamd not found yet, retrying (5/1800) ...
Socket for clamd not found yet, retrying (6/1800) ...
Socket for clamd not found yet, retrying (7/1800) ...
Socket for clamd not found yet, retrying (8/1800) ...
Socket for clamd not found yet, retrying (9/1800) ...
Socket for clamd not found yet, retrying (10/1800) ...
Socket for clamd not found yet, retrying (11/1800) ...
Socket for clamd not found yet, retrying (12/1800) ...
Socket for clamd not found yet, retrying (13/1800) ...
Socket for clamd not found yet, retrying (14/1800) ...
Socket for clamd not found yet, retrying (15/1800) ...
Socket for clamd not found yet, retrying (16/1800) ...
Socket for clamd not found yet, retrying (17/1800) ...
Socket for clamd not found yet, retrying (18/1800) ...
Socket for clamd not found yet, retrying (19/1800) ...
Socket for clamd not found yet, retrying (20/1800) ...
Socket for clamd not found yet, retrying (21/1800) ...
Socket for clamd not found yet, retrying (22/1800) ...
Socket for clamd not found yet, retrying (23/1800) ...
Socket for clamd not found yet, retrying (24/1800) ...
Socket for clamd not found yet, retrying (25/1800) ...
Socket for clamd not found yet, retrying (26/1800) ...
Socket for clamd not found yet, retrying (27/1800) ...
Socket for clamd not found yet, retrying (28/1800) ...
Socket for clamd not found yet, retrying (29/1800) ...
Socket for clamd not found yet, retrying (30/1800) ...
Socket for clamd not found yet, retrying (31/1800) ...
Socket for clamd not found yet, retrying (32/1800) ...
Socket for clamd not found yet, retrying (33/1800) ...
Socket for clamd not found yet, retrying (34/1800) ...
Socket for clamd not found yet, retrying (35/1800) ...
Socket for clamd not found yet, retrying (36/1800) ...
Socket for clamd not found yet, retrying (37/1800) ...
Socket for clamd not found yet, retrying (38/1800) ...
Socket for clamd not found yet, retrying (39/1800) ...
Socket for clamd not found yet, retrying (40/1800) ...
Socket for clamd not found yet, retrying (41/1800) ...
Socket for clamd not found yet, retrying (42/1800) ...
Socket for clamd not found yet, retrying (43/1800) ...
Socket for clamd not found yet, retrying (44/1800) ...
Socket for clamd not found yet, retrying (45/1800) ...
Socket for clamd not found yet, retrying (46/1800) ...
Socket for clamd not found yet, retrying (47/1800) ...
Socket for clamd not found yet, retrying (48/1800) ...
Socket for clamd not found yet, retrying (49/1800) ...
Socket for clamd not found yet, retrying (50/1800) ...Mon Sep  7 22:10:54 2026 -> Limits: Global time limit set to 120000 milliseconds.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: Global size limit set to 419430400 bytes.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: File size limit set to 104857600 bytes.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: Recursion level limit set to 17.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: Files limit set to 10000.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: MaxEmbeddedPE limit set to 41943040 bytes.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: MaxHTMLNormalize limit set to 41943040 bytes.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: MaxHTMLNoTags limit set to 8388608 bytes.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: MaxScriptNormalize limit set to 20971520 bytes.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: MaxZipTypeRcg limit set to 1048576 bytes.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: MaxPartitions limit set to 50.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: MaxIconsPE limit set to 100.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: MaxRecHWP3 limit set to 16.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: PCREMatchLimit limit set to 100000.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: PCRERecMatchLimit limit set to 2000.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Limits: PCREMaxFileSize limit set to 104857600.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Archive support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Image (graphics) scanning support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Detection using image fuzzy hash enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Heuristic alerting enabled for scans that exceed set maximums.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Heuristic alerts enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Portable Executable support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> ELF support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Mail files support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> OLE2 support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> PDF support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> SWF support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> HTML support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> XMLDOCS support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> HWP3 support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> OneNote support enabled.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Self checking every 600 seconds.
clamav-1  | Mon Sep  7 22:10:54 2026 -> Set stacksize to 1048576
clamav-1  | socket found, clamd started.

```


## Unit tests and regression

Exact successful command:

```powershell
docker run --rm --network none -e DATABASE_URL=sqlite:////tmp/security-unit.db -e STORAGE_PATH=/tmp/security-unit-storage --mount type=bind,source=C:/Users/ss/Desktop/XAI/XAI/services/api_fastapi/tests,target=/tests,readonly xai-backend python -m pytest /tests/test_security_scanner.py /tests/test_integration_boundaries.py -q -p no:cacheprovider
```

The initial run failed collection with two `IndexError: 3` errors: the container-default selector resolver assumed a repository directory depth. Fixed the fallback to discover the repository or use the installed engine package location. The successful rerun uses the rebuilt image and no selector-path environment override.

```text
SECURITY_TESTS_COLLECTED=12
SECURITY_TESTS_PASSED=12
SECURITY_TESTS_FAILED=0
BOUNDARY_REGRESSION_TESTS_PASSED=8
PYTEST_SUMMARY=20 passed, 6 warnings in 12.09s
```

Warnings: Starlette/httpx deprecation, Python crypt deprecation, and four SQLAlchemy datetime.utcnow deprecations. No test failures remain. ClamAV is mocked only in isolated unit tests. Real YARA compilation and detection also run in that suite. The real daemon was separately exercised below.

The blocked-upload tests replace compression with a function that fails if invoked, and verify HTTP 422/503 plus directory cleanup. The decompressed-output test records and asserts `['decompress', 'scan']`, returns 422, and verifies neither marker bytes nor a restored file are released.

```text
DECOMPRESS_OCCURRED=True
OUTPUT_SCAN_OCCURRED=True
RELEASE_OCCURRED=False
```

Local hybrid-v2 round-trips were re-executed: README.md 3182 -> 1683 -> 3182 bytes; deployment/README.md 14649 -> 6065 -> 14649 bytes. Both hashes match the previously recorded full hashes. Selector artifact and all profiles loaded with C:\Python314\python.exe from both root and services/api_fastapi. No models were retrained.

## Runtime YARA and real ClamAV proof

Inside rebuilt backend, actual rules were compiled and matched against harmless clean bytes and the synthetic marker. A harmless file was created using TemporaryDirectory under settings.storage_root, scanned with the real scan_file abstraction, and removed.

```text
YARA_MODULE_AVAILABLE=True
YARA_RULES_PATH=/app/security/yara
YARA_RULES_COMPILE=PASS
YARA_RULE_COUNT=1
YARA_CLEAN_MATCHES=[]
YARA_TEST_MATCH=XAI_Synthetic_Security_Test
CLAMAV_AVAILABLE=True
CLAMAV_CLEAN_SCAN_STATUS=clean
CLAMAV_CLEAN=True
REAL_SCAN_SHA256=ae9deafe39c9eb544b91e6b704b2190127df5b69802741ecdea069e239ee478c
REAL_SCAN_CLAMAV_MATCHES=[]
REAL_SCAN_YARA_MATCHES=[]
REAL_SCAN_ERROR=None
```

## Authenticated Docker execution

Executed `C:\Python314\python.exe scripts/test_security_pipeline.py`, exit 0. Registered a disposable local user, logged in, uploaded deployment/README.md, downloaded its artifact and decompressed it. Real structured scanner logs associate clean ClamAV/YARA results with the full input/output hash. Uploaded synthetic marker was rejected with 422. A separately constructed harmless synthetic XAIC fixture was decompressed by the API and rejected with 422 before release.

With SECURITY_SCAN_REQUIRED=True, the script stopped only ClamAV, checked sanitized 503 rejections on both compression and decompression, checked public degraded/unavailable state, and restarted ClamAV in finally. Restoration reached readiness and the later Docker health probe also confirmed healthy. No scanner bypass was enabled.

Final disposable-user database/storage checks: one FileRecord, status completed; one retained successful job directory; zero decompression temporary directories. Rejected requests created no additional completed job records. Unit control-flow checks separately prove compression is not invoked following rejection.

Actual captured output:


```text
REGISTER_STATUS=200
AUTH_STATUS=200
COMPRESSION_HTTP_STATUS=200
JOB_ID=ab0609f96f2c37586284c84e
JOB_STATUS=completed
ARTIFACT_HTTP_STATUS=200
ARTIFACT_BYTES=6065
DECOMPRESSION_HTTP_STATUS=200
SHA256_SECURITY_ORIGINAL=2aeac16b1ec1cd6d3c273fd353d2acfe97ed326108e337e6151e9d8245854939
SHA256_SECURITY_RESTORED=2aeac16b1ec1cd6d3c273fd353d2acfe97ed326108e337e6151e9d8245854939
SECURITY_HASH_EQUAL=True
SHA256_DOCKER_SECURITY_ORIGINAL=2aeac16b1ec1cd6d3c273fd353d2acfe97ed326108e337e6151e9d8245854939
SHA256_DOCKER_SECURITY_RESTORED=2aeac16b1ec1cd6d3c273fd353d2acfe97ed326108e337e6151e9d8245854939
DOCKER_SECURITY_HASH_EQUAL=True
YARA_BLOCK_HTTP_STATUS=422
YARA_BLOCKED=True
YARA_OUTPUT_BLOCK_HTTP_STATUS=422
CLAMAV_STOPPED=True
FAIL_CLOSED_HTTP_STATUS=503
FAIL_CLOSED_RESPONSE={"detail":"File security verification unavailable; retry later"}
FAIL_CLOSED=True
OUTPUT_FAIL_CLOSED_HTTP_STATUS=503
UNAVAILABLE_PUBLIC_STATUS={"status":"degraded","services":{"api":"operational","identity":"operational","compression":"operational","storage":"operational","notifications":"degraded","security_scanner":"unavailable"}}
CLAMAV_RESTORED=True
PUBLIC_STATUS_HTTP_STATUS=200
PUBLIC_STATUS_BODY={"status":"degraded","services":{"api":"operational","identity":"operational","compression":"operational","storage":"operational","notifications":"degraded","security_scanner":"operational"}}
PUBLIC_STATUS_SECURITY=operational
BACKEND_HTTP_STATUS=200
BACKEND_HEALTH_BODY={"status":"ok","service":"xai-platform-api","compression":{"mode":"hybrid-v2","runtime_generation":"v3","routing":"top3","selector_v2":true}}
UPLOAD_CLAMAV_STATUS=clean
UPLOAD_YARA_STATUS=clean
OUTPUT_CLAMAV_STATUS=clean
OUTPUT_YARA_STATUS=clean
YARA_MATCH=XAI_Synthetic_Security_Test
DOCKER_CLAMAV=PASS
DOCKER_YARA=PASS
DOCKER_SECURITY_PIPELINE=PASS
```


Raw structured scan events are saved in `scratch/security-validation/scan-events.json`; raw execution fields in `results.json`; final ClamAV health/logs in `clamav-health.json` and `clamav-recent.log`. Original prior report hashes were not replaced. No credentials or tokens are persisted in these evidence files. The disposable account and its one successful artifact remain in the local development database/storage.

## Final executed security statuses

```text
CLAMAV HEALTH: PASS
REAL CLAMAV CLEAN SCAN: PASS
YARA LOAD: PASS
YARA SYNTHETIC DETECTION: PASS
UPLOAD SECURITY GATE: PASS
DECOMPRESSION OUTPUT GATE: PASS
FAIL-CLOSED POLICY: PASS
SECURITY TEST SUITE: PASS
DOCKER SECURITY PIPELINE: PASS
SECURITY SHA256 INTEGRITY: PASS
CLAMAV: PASS
YARA: PASS
DECOMPRESSION SECURITY GATE: PASS
DOCKER CLAMAV: PASS
DOCKER YARA: PASS
SECURITY PIPELINE: PASS
PUBLIC STATUS SECURITY: operational
```

Public overall status remains degraded because notifications are degraded; compression and security_scanner are operational. Public JSON contains no scanner host, port, path, rule name, signature, or internal exception. Scanner PASS here establishes executed clean scans and synthetic blocking behavior, not general malware-detection coverage. No real malware samples were used. The standalone compression engine remains unchanged.
