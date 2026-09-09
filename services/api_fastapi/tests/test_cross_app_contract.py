"""Logical integration only: HTTP email, ClamAV, and compression engine are mocked."""
import json
import re
import pyotp
from app import main, mfa, email_service, security_scanner
from app.config import settings
from test_mfa_enrollment import flow


def test_brevo_mfa_login_compression_history_download_logout(flow, monkeypatch, tmp_path):
    import xai_compress.compression as codec
    client, engine, sent = flow
    credentials={'email':'person@example.com','password':'correct-password'}
    monkeypatch.setattr(settings,'email_provider','brevo')
    monkeypatch.setattr(settings,'brevo_api_key','unit-test-placeholder')
    monkeypatch.setattr(settings,'brevo_sender_email','sender@example.com')
    monkeypatch.setattr(settings,'storage_path',str(tmp_path))
    monkeypatch.setattr(settings,'max_upload_bytes',1048576)
    monkeypatch.setattr(settings,'max_decompressed_bytes',1048576)
    monkeypatch.setattr(settings,'min_free_disk_bytes',16777216)
    monkeypatch.setattr(mfa,'send_verification_code',email_service.send_verification_code)
    messages=[]
    class Reply:
        status=201
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return b'{"messageId":"unit-message"}'
    def send(request,timeout):
        messages.append(json.loads(request.data));return Reply()
    monkeypatch.setattr(email_service.urllib.request,'urlopen',send)
    initial=client.post('/auth/login',json=credentials)
    assert initial.status_code==200
    enrollment=client.post('/auth/totp/enroll',json={})
    assert enrollment.status_code==200 and 'secret' not in enrollment.json()
    assert len(messages)==1 and messages[0]['to']==[{'email':credentials['email']}]
    code=re.search(r'\b[0-9]{6}\b',messages[0]['textContent']).group()
    eid=enrollment.json()['enrollment_id']
    disclosure=client.post('/auth/totp/email/confirm',json={'enrollment_id':eid,'code':code})
    assert disclosure.status_code==200
    secret=disclosure.json()['secret']
    assert secret not in json.dumps(messages)
    assert client.post('/auth/totp/confirm',json={'enrollment_id':eid,'code':pyotp.TOTP(secret).now()}).status_code==200
    assert client.post('/auth/logout',json={'refresh_token':initial.json()['refresh_token']}).status_code==200
    client.headers.pop('Authorization')
    assert client.post('/auth/login',json=credentials).status_code==401
    login=client.post('/auth/login',json={**credentials,'totp_code':pyotp.TOTP(secret).now()})
    assert login.status_code==200
    tokens=login.json();client.headers['Authorization']='Bearer '+tokens['access_token']
    monkeypatch.setattr(security_scanner,'clamav_scan',lambda p:('clean',[]))
    def compress(source,artifact,**kwargs):artifact.write_bytes(b'XAIC\x06'+source.read_bytes());return {}
    def decompress(artifact,restored,**kwargs):restored.write_bytes(artifact.read_bytes()[5:]);return {}
    monkeypatch.setattr(codec,'compress_file',compress)
    monkeypatch.setattr(codec,'decompress_file',decompress)
    original=b'logical integration bytes'
    job=client.post('/compression/jobs',files={'upload':('sample.txt',original)})
    assert job.status_code==200
    fid=job.json()['id']
    assert any(row['id']==fid for row in client.get('/history').json())
    download=client.get(f'/files/{fid}/download')
    assert download.status_code==200 and download.content==b'XAIC\x06'+original
    assert client.post('/auth/logout',json={'refresh_token':tokens['refresh_token']}).status_code==200
    client.headers.pop('Authorization')
    assert client.get('/history').status_code==401
    assert client.post('/auth/refresh',json={'refresh_token':tokens['refresh_token']}).status_code==401
