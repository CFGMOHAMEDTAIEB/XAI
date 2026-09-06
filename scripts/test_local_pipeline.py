"""Diagnostic real-service subset; never declares the full email/mobile/UI E2E passed."""
import json
from pathlib import Path
import secrets
from test_full_e2e import Api, sha


def main():
    api = Api('http://localhost:4200/api')
    output = Path('dist/e2e-diagnostic')
    output.mkdir(parents=True, exist_ok=True)
    account = {'email': 'e2e-' + secrets.token_hex(6) + '@example.com', 'password': secrets.token_urlsafe(24)}
    api.token = api.call('/auth/register', account)['access_token']
    original = (b'XAI integration test: actual Hybrid V3 compression, untrusted attachment import, SHA-256.\r\n' * 24000
                + bytes(range(256)) * 16)
    name = 'xai-e2e-original.bin'
    (output / name).write_bytes(original)
    job = api.call('/compression/jobs', upload=(name, original))
    artifact = api.call(f"/files/{job['id']}/download")
    (output / (name + '.xaic')).write_bytes(artifact)
    restored = api.call('/compression/decompress', upload=(name + '.xaic', artifact))
    (output / ('restored-' + name)).write_bytes(restored)
    assert original == restored and job['sha256'] == sha(original)
    assert job['integrity_verified'] and len(artifact) == job['compressed_size']
    rejected = []
    for label, payload in [('fake extension', b'not a container'), ('truncated', artifact[:20]),
                           ('corrupt', artifact[:-1] + bytes([artifact[-1] ^ 1]))]:
        try:
            api.call('/compression/decompress', upload=('untrusted.xaic', payload))
        except RuntimeError as exc:
            assert 'HTTP 400' in str(exc), str(exc)
            rejected.append(label)
        else:
            raise AssertionError(f'{label} was accepted')
    other = Api(api.base)
    other.token = other.call('/auth/register', {'email': 'e2e-other-' + secrets.token_hex(6) + '@example.com',
                                              'password': secrets.token_urlsafe(24)})['access_token']
    try:
        other.call(f"/files/{job['id']}/download")
    except RuntimeError as exc:
        assert 'HTTP 404' in str(exc)
    else:
        raise AssertionError('Cross-account artifact download allowed')
    email = {'result': 'not attempted', 'reason': 'External delivery is separate from local diagnostics'}
    report = {'scope': 'live API/proxy diagnostic; not full E2E', 'job_id': job['id'],
              'codec': job['codec'], 'original_filename': name, 'original_size': len(original),
              'compressed_filename': name + '.xaic', 'compressed_size': len(artifact),
              'compression_ratio': len(original)/len(artifact), 'saving_percent': 100*(1-len(artifact)/len(original)),
              'ORIGINAL_SHA256': sha(original), 'DECOMPRESSED_SHA256': sha(restored),
              'artifact_sha256': sha(artifact), 'binary_equal': original == restored,
              'rejected_attachments': rejected, 'cross_account_download': 'rejected', 'email': email,
              'full_e2e': 'FAIL: email receipt and browser UI/mobile authentication not verified by this diagnostic'}
    (output / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
