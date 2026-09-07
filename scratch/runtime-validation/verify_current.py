import ast
import hashlib
import json
import secrets
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sha = lambda data: hashlib.sha256(data).hexdigest()

def emit(key, value):
    print(f'{key}={value}', flush=True)

def profiles():
    from xai_compress.hybrid.profiles import load_profiles, DEFAULT_PROFILE_PATH
    values = load_profiles()
    emit('HYBRID_PROFILES_PATH', DEFAULT_PROFILE_PATH)
    emit('PROFILE_KEYS', json.dumps(list(values)))
    emit('BALANCED_PROFILE', json.dumps(values['balanced']))
    emit('PROFILE_LOADER', 'xai_compress.hybrid.profiles.load_profiles')

def paths():
    sys.path.insert(0, str(ROOT))
    from services.api_fastapi.app.config import settings
    from xai_compress.hybrid.selector import HybridSelector
    from xai_compress.hybrid.profiles import load_profiles
    selector = HybridSelector(profile='balanced', mode='ai-benchmark', top_k=3, microbench_bytes=65536, model_path=settings.selector_model_path)
    artifact, error = selector._load_artifact()
    emit('PYTHON', sys.executable)
    emit('CWD', Path.cwd())
    emit('SELECTOR_PATH', settings.selector_model_path)
    emit('SELECTOR_LOADED', artifact is not None)
    emit('SELECTOR_ERROR', error)
    emit('CWD_TEST', 'PASS' if artifact is not None and 'balanced' in load_profiles() else 'FAIL')

def local():
    from xai_compress.compression import compress_file, decompress_file
    for label, source in [('FIRST', ROOT/'README.md'), ('SECOND', ROOT/'deployment/README.md')]:
        artifact = OUT / (label.lower()+'.xaic')
        restored = OUT / (label.lower()+'_restored.md')
        emit('TEST', label)
        emit('ORIGINAL_PATH', source)
        emit('ORIGINAL_BYTES', source.stat().st_size)
        emit('FILE_TYPE', 'UTF-8 Markdown text' if source.read_text(encoding='utf-8') else 'empty')
        start = time.perf_counter()
        compress_file(source, artifact, mode='hybrid-v2', profile='balanced', selector_model=str(ROOT/'engines/XAI-Compress/checkpoints/selector_v2/best.json'), overwrite=True)
        emit('COMPRESSION_SECONDS', f'{time.perf_counter()-start:.6f}')
        start = time.perf_counter()
        decompress_file(artifact, restored, overwrite=True)
        emit('DECOMPRESSION_SECONDS', f'{time.perf_counter()-start:.6f}')
        emit('XAIC_PATH', artifact)
        emit('XAIC_BYTES', artifact.stat().st_size)
        emit('RESTORED_PATH', restored)
        emit('RESTORED_BYTES', restored.stat().st_size)
        emit('SHA256_ORIGINAL', sha(source.read_bytes()))
        emit('SHA256_RESTORED', sha(restored.read_bytes()))
        emit('HASH_EQUAL', source.read_bytes() == restored.read_bytes())

def http():
    base = sys.argv[2] if len(sys.argv)>2 else 'http://127.0.0.1:8000'
    tag = sys.argv[3] if len(sys.argv)>3 else 'API'
    def request(path, data=None, token=None, content_type=None):
        headers = {}
        if token: headers['Authorization'] = 'Bearer '+token
        if content_type: headers['Content-Type'] = content_type
        req = urllib.request.Request(base+path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=180) as r: return r.status, r.read()
        except urllib.error.HTTPError as e: return e.code, e.read()
    for path, key in [('/health','HEALTH'),('/public/status','PUBLIC_STATUS')]:
        code, body = request(path)
        emit(key+'_HTTP_STATUS', code)
        emit(key+'_BODY', body.decode())
    credentials = {'email':'runtime-'+secrets.token_hex(8)+'@example.com', 'password':secrets.token_urlsafe(24), 'display_name':'Temporary runtime verification'}
    code, body = request('/auth/register', json.dumps(credentials).encode(), content_type='application/json')
    emit('REGISTER_STATUS', code)
    if code != 200: emit('REGISTER_ERROR', body.decode()); return
    code, body = request('/auth/login', json.dumps(credentials).encode(), content_type='application/json')
    emit('AUTH_ENDPOINT', base+'/auth/login')
    emit('AUTH_STATUS', code)
    if code != 200: emit('AUTH_ERROR', body.decode()); return
    token = json.loads(body)['access_token']
    def upload(path, name, data):
        boundary = 'XAI'+secrets.token_hex(12)
        payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="upload"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+data+f'\r\n--{boundary}--\r\n'.encode())
        return request(path, payload, token, 'multipart/form-data; boundary='+boundary)
    source = (ROOT/'deployment/README.md').read_bytes()
    code, body = upload('/compression/jobs', 'runtime-second.md', source)
    emit('COMPRESSION_ENDPOINT', base+'/compression/jobs')
    emit('COMPRESSION_STATUS', code)
    if code != 200: emit('COMPRESSION_ERROR', body.decode()); return
    job = json.loads(body)
    emit('JOB_ID', job['job_id'])
    emit('JOB_STATUS', job['status'])
    endpoint = '/files/'+str(job['id'])+'/download'
    code, artifact = request(endpoint, token=token)
    emit('ARTIFACT_ENDPOINT', base+endpoint)
    emit('ARTIFACT_STATUS', code)
    emit('ARTIFACT_BYTES', len(artifact))
    if code != 200: return
    (OUT/(tag.lower()+'_artifact.xaic')).write_bytes(artifact)
    code, restored = upload('/compression/decompress', 'runtime-second.md.xaic', artifact)
    emit('DECOMPRESSION_ENDPOINT', base+'/compression/decompress')
    emit('DECOMPRESSION_STATUS', code)
    if code != 200: emit('DECOMPRESSION_ERROR', restored.decode()); return
    (OUT/(tag.lower()+'_restored.md')).write_bytes(restored)
    emit('SHA256_'+tag+'_ORIGINAL', sha(source))
    emit('SHA256_'+tag+'_RESTORED', sha(restored))
    emit(tag+'_HASH_EQUAL', source == restored)

def routes():
    tree = ast.parse((ROOT/'services/api_fastapi/app/main.py').read_text())
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.args and isinstance(d.args[0], ast.Constant):
                    path = d.args[0].value
                    if path in ('/auth/register','/auth/login','/compression/jobs','/compression/decompress','/files/{file_id}/download','/history'):
                        print(f'{d.func.attr.upper()} {path} -> {node.name}')

if __name__ == '__main__':
    globals()[sys.argv[1]]()
