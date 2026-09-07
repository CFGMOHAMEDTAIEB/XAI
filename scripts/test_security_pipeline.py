"""Live Docker security checks using harmless fixtures, with daemon restoration."""
import hashlib, json, secrets, subprocess, time, urllib.request, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'scratch/security-validation'
results = {}
def emit(key, value):
    results[key] = value
    print(f'{key}={value}', flush=True)
    (OUT/'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
def compose(*args):
    return subprocess.check_output(['docker', 'compose', *args], cwd=ROOT, text=True, timeout=120)
def request(path, data=None, token=None, kind='application/json'):
    headers = {'Content-Type': kind}
    if token: headers['Authorization'] = 'Bearer '+token
    try:
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000'+path, data=data, headers=headers), timeout=120) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
def upload(path, name, data, token):
    boundary = secrets.token_hex(16)
    body = f'--{boundary}\r\nContent-Disposition: form-data; name="upload"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+data+f'\r\n--{boundary}--\r\n'.encode()
    return request(path, body, token, 'multipart/form-data; boundary='+boundary)
def ready():
    deadline = time.monotonic()+180
    while time.monotonic()<deadline:
        try:
            code, body = request('/public/status')
            if code == 200 and json.loads(body)['services'].get('security_scanner') == 'operational': return
        except Exception: pass
        time.sleep(3)
    raise RuntimeError('Scanner did not become ready within 180 seconds')
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ready()
    credentials = json.dumps({'email':'security-'+secrets.token_hex(8)+'@example.com', 'password':secrets.token_urlsafe(24)}).encode()
    code, body = request('/auth/register', credentials); emit('REGISTER_STATUS', code); assert code == 200, body
    code, body = request('/auth/login', credentials); emit('AUTH_STATUS', code); assert code == 200, body
    token = json.loads(body)['access_token']
    original = (ROOT/'deployment/README.md').read_bytes()
    code, body = upload('/compression/jobs', 'README.md', original, token)
    emit('COMPRESSION_HTTP_STATUS', code); assert code == 200, body
    job = json.loads(body); emit('JOB_ID', job['job_id']); emit('JOB_STATUS', job['status'])
    code, artifact = request('/files/'+str(job['id'])+'/download', token=token)
    emit('ARTIFACT_HTTP_STATUS', code); emit('ARTIFACT_BYTES', len(artifact)); assert code == 200
    (OUT/'clean.xaic').write_bytes(artifact)
    code, restored = upload('/compression/decompress', 'README.md.xaic', artifact, token)
    emit('DECOMPRESSION_HTTP_STATUS', code); assert code == 200, restored
    (OUT/'restored.md').write_bytes(restored)
    for tag in ('SECURITY', 'DOCKER_SECURITY'):
        emit('SHA256_'+tag+'_ORIGINAL', hashlib.sha256(original).hexdigest())
        emit('SHA256_'+tag+'_RESTORED', hashlib.sha256(restored).hexdigest())
        emit(tag+'_HASH_EQUAL', original == restored)
    assert original == restored
    marker = b'Harmless fixture XAI_SECURITY_TEST_MARKER\n'
    code, body = upload('/compression/jobs', 'synthetic.txt', marker, token)
    emit('YARA_BLOCK_HTTP_STATUS', code); emit('YARA_BLOCKED', code == 422); assert code == 422, body
    from xai_compress.compression import compress_file
    source = OUT/'synthetic.txt'; source.write_bytes(marker)
    target = OUT/'synthetic.xaic'
    compress_file(source, target, mode='hybrid-v2', profile='balanced', selector_model=str(ROOT/'engines/XAI-Compress/checkpoints/selector_v2/best.json'), overwrite=True)
    code, body = upload('/compression/decompress', 'synthetic.xaic', target.read_bytes(), token)
    emit('YARA_OUTPUT_BLOCK_HTTP_STATUS', code); assert code == 422, body
    try:
        compose('stop', 'clamav'); emit('CLAMAV_STOPPED', True)
        code, body = upload('/compression/jobs', 'clean.txt', b'Harmless outage test', token)
        emit('FAIL_CLOSED_HTTP_STATUS', code); emit('FAIL_CLOSED_RESPONSE', body.decode()); emit('FAIL_CLOSED', code == 503); assert code == 503, body
        code, body = upload('/compression/decompress', 'README.md.xaic', artifact, token)
        emit('OUTPUT_FAIL_CLOSED_HTTP_STATUS', code); assert code == 503, body
        code, body = request('/public/status'); emit('UNAVAILABLE_PUBLIC_STATUS', body.decode())
        assert json.loads(body)['services']['security_scanner'] == 'unavailable'
        assert json.loads(body)['status'] == 'degraded'
    finally:
        compose('start', 'clamav'); ready(); emit('CLAMAV_RESTORED', True)
    code, body = request('/public/status'); emit('PUBLIC_STATUS_HTTP_STATUS', code); emit('PUBLIC_STATUS_BODY', body.decode())
    emit('PUBLIC_STATUS_SECURITY', json.loads(body)['services']['security_scanner'])
    code, body = request('/health'); emit('BACKEND_HTTP_STATUS', code); emit('BACKEND_HEALTH_BODY', body.decode())
    scans = [json.loads(line.split('security_scan ',1)[1]) for line in compose('logs','--no-color','backend').splitlines() if 'security_scan {' in line]
    (OUT/'scan-events.json').write_text(json.dumps(scans,indent=2),encoding='utf-8')
    for stage, tag in [('upload','UPLOAD'), ('decompressed_output','OUTPUT')]:
        scan = next(s for s in scans if s['stage'] == stage and s['sha256'] == hashlib.sha256(original).hexdigest() and s['clean'])
        emit(tag+'_CLAMAV_STATUS', scan['clamav_status']); emit(tag+'_YARA_STATUS', scan['yara_status'])
    scan = next(s for s in scans if s['sha256'] == hashlib.sha256(marker).hexdigest() and s['yara_matches'])
    emit('YARA_MATCH', ','.join(scan['yara_matches']))
    for key in ('DOCKER_CLAMAV', 'DOCKER_YARA', 'DOCKER_SECURITY_PIPELINE'): emit(key, 'PASS')
if __name__ == '__main__': main()
