import hashlib, json, secrets, urllib.request, urllib.error
BASE = 'https://xai-1-be9s.onrender.com'
def call(route, data=None, token=None, content_type='application/json'):
    headers = {'Content-Type': content_type}
    if token: headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + route, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as r: return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
def js(route, value, token=None): return call(route, json.dumps(value).encode(), token)
account = {'email': 'client-release-' + secrets.token_hex(8) + '@example.com', 'password': secrets.token_urlsafe(32)}
s, b = js('/auth/register', account); print('register', s, flush=True)
assert s == 200, b
registration = json.loads(b)
s, b = js('/auth/login', account); print('login', s, flush=True)
assert s == 200, b
session = json.loads(b); token = session['access_token']
for route in ['/auth/me', '/history']:
    s, b = call(route, token=token); print(route, s, flush=True); assert s == 200
original = b'XAI production client connectivity validation.\n' * 128
def multipart(route, name, data):
    boundary = 'xai' + secrets.token_hex(16)
    payload = ('--' + boundary + '\r\nContent-Disposition: form-data; name="upload"; filename="' + name + '"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + data + ('\r\n--' + boundary + '--\r\n').encode()
    return call(route, payload, token, 'multipart/form-data; boundary=' + boundary)
s, b = multipart('/compression/jobs', 'validation.txt', original)
print('compression', s, b.decode()[:1500], flush=True)
if s == 200:
    job = json.loads(b); s, artifact = call('/files/' + str(job['id']) + '/download', token=token)
    print('download', s, len(artifact), flush=True); assert s == 200
    s, restored = multipart('/compression/decompress', 'validation.txt.xaic', artifact)
    print('decompression', s, flush=True); assert s == 200
    assert hashlib.sha256(original).digest() == hashlib.sha256(restored).digest()
    print('SHA256 equality PASS', hashlib.sha256(restored).hexdigest())
for pair in [registration, session]:
    if pair.get('refresh_token'): print('logout', js('/auth/logout', {'refresh_token': pair['refresh_token']})[0])
