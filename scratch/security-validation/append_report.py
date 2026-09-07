import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
results = json.loads((out/'results.json').read_text())
assert results['DOCKER_SECURITY_PIPELINE'] == 'PASS'
def docker(*args):
    return subprocess.check_output(['docker', *args], cwd=root, text=True, timeout=30)
health = json.loads(docker('inspect', 'xai-clamav-1', '--format', '{{json .State.Health}}'))
assert health['Status'] == 'healthy'
logs = docker('compose', 'logs', '--tail=42', 'clamav')
(out/'clamav-health.json').write_text(json.dumps(health, indent=2), encoding='utf-8')
(out/'clamav-recent.log').write_text(logs, encoding='utf-8')
sections = ['''

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
''', '\nCLAMAV_HEALTH_LOG=\n```json\n'+json.dumps(health,indent=2)+'\n```\n', '\nCLAMAV_RECENT_LOGS=\n```text\n'+logs+'\n```\n', '''
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

Local hybrid-v2 round-trips were re-executed: README.md 3182 -> 1683 -> 3182 bytes; deployment/README.md 14649 -> 6065 -> 14649 bytes. Both hashes match the previously recorded full hashes. Selector artifact and all profiles loaded with C:\\Python314\\python.exe from both root and services/api_fastapi. No models were retrained.

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

Executed `C:\\Python314\\python.exe scripts/test_security_pipeline.py`, exit 0. Registered a disposable local user, logged in, uploaded deployment/README.md, downloaded its artifact and decompressed it. Real structured scanner logs associate clean ClamAV/YARA results with the full input/output hash. Uploaded synthetic marker was rejected with 422. A separately constructed harmless synthetic XAIC fixture was decompressed by the API and rejected with 422 before release.

With SECURITY_SCAN_REQUIRED=True, the script stopped only ClamAV, checked sanitized 503 rejections on both compression and decompression, checked public degraded/unavailable state, and restarted ClamAV in finally. Restoration reached readiness and the later Docker health probe also confirmed healthy. No scanner bypass was enabled.

Final disposable-user database/storage checks: one FileRecord, status completed; one retained successful job directory; zero decompression temporary directories. Rejected requests created no additional completed job records. Unit control-flow checks separately prove compression is not invoked following rejection.

Actual captured output:
''', '\n```text\n'+'\n'.join(f'{k}={v}' for k,v in results.items())+'\n```\n', '''
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
''']
report = root/'docs/XAI_E2E_REPORT.md'
prior = report.read_text(encoding='utf-8')
heading = '# Executed security integration — 2026-09-08 Europe/Paris'
assert heading not in prior, 'Security report already appended'
report.write_text(prior+'\n'.join(sections), encoding='utf-8')
print('REPORT_UPDATED='+str(report))
