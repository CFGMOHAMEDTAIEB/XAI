"""Local real ClamAV + production YARA validation; no production configuration changes."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
from fastapi import HTTPException
from app import security_scanner as scanner
from app.config import settings

settings.app_env = 'production'
settings.yara_rules_path = '/repo/services/api_fastapi/security/yara/production'
root = settings.storage_root
root.mkdir(parents=True, exist_ok=True)
report = {'environment': 'LOCAL ONLY', 'health': scanner.scanner_health(), 'scans': []}
assert report['health']['status'] == 'operational', report
with tempfile.TemporaryDirectory(prefix='production-rules-', dir=root) as work:
    work = Path(work)
    for relative in ['README.md', 'engines/XAI-Compress/checkpoints/selector_v2/best.json',
                     'scratch/security-validation/clean.xaic', 'scratch/security-validation/restored.md']:
        source = Path('/repo') / relative
        target = work / source.name
        target.write_bytes(source.read_bytes())
        result = scanner.enforce_scan(target, 'local-clean-fixture', hashlib.sha256(target.read_bytes()).hexdigest())
        report['scans'].append({'fixture': relative, **asdict(result)})
    original = b'XAI production scanner clean fixture\n' * 128
    source = work / 'original.txt'; source.write_bytes(original)
    upload = scanner.enforce_scan(source, 'upload', hashlib.sha256(original).hexdigest())
    from xai_compress.compression import compress_file, decompress_file
    artifact = work / 'artifact.xaic'; restored = work / 'restored.txt'
    compress_file(source, artifact, mode='hybrid-v2', profile='balanced', selector_model=settings.selector_model_path, overwrite=True)
    decompress_file(artifact, restored, overwrite=True, max_output_size=settings.max_decompressed_bytes)
    output = scanner.enforce_scan(restored, 'output')
    report['roundtrip'] = {'original_bytes': len(original), 'xaic_bytes': artifact.stat().st_size,
                           'restored_bytes': restored.stat().st_size, 'upload': asdict(upload), 'output': asdict(output),
                           'hash_equal': hashlib.sha256(original).hexdigest() == output.sha256}
    assert report['roundtrip']['hash_equal']
    original_connect = scanner._connect
    def unavailable(timeout):
        raise ConnectionRefusedError('isolated local test')
    scanner._connect = unavailable
    try:
        scanner.enforce_scan(source, 'local-unavailable-test')
        raise AssertionError('Unavailable scanner permitted release')
    except HTTPException as exc:
        assert exc.status_code == 503
        report['fail_closed_http_status'] = exc.status_code
    finally:
        scanner._connect = original_connect
    report['health_after_test'] = scanner.scanner_health()
    assert report['health_after_test']['status'] == 'operational'
print(json.dumps(report, indent=2, sort_keys=True))
