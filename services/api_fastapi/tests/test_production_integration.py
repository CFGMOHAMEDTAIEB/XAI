import base64
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app import email_service

def test_public_status_has_no_secrets():
    data=TestClient(app).get('/public/status').json()
    assert set(data)=={'status','services'}
    assert set(data['services'])=={'api','identity','compression','storage','notifications','security_scanner'}
    assert set(data['services'].values())<= {'operational','unknown','unavailable','degraded'}
    assert data['services']['notifications']!='operational'

def test_brevo_missing_key_never_sends(monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'email_provider','brevo');monkeypatch.setattr(settings,'brevo_api_key','')
    with pytest.raises(ValueError,match='BREVO_API_KEY'):
        email_service.send_artifact(tmp_path/'unused','original.xaic','recipient@example.com')

def test_brevo_xaic_restriction_is_not_bypassed(monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'email_provider','brevo');monkeypatch.setattr(settings,'brevo_api_key','test-key');monkeypatch.setattr(settings,'brevo_sender_email','sender@example.com')
    with pytest.raises(ValueError,match='allowlist'):
        email_service.send_artifact(tmp_path/'unused','original.xaic','recipient@example.com')

def test_brevo_https_payload_and_acknowledgement(monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'email_provider','brevo');monkeypatch.setattr(settings,'brevo_api_key','test-key');monkeypatch.setattr(settings,'brevo_sender_email','sender@example.com')
    payload=b'Unit test text';path=tmp_path/'test.txt';path.write_bytes(payload)
    class Response:
        status=201
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return b'{"messageId":"<unit-test>"}'
    def send(request,timeout):
        assert request.full_url=='https://api.brevo.com/v3/smtp/email'
        body=json.loads(request.data)
        assert base64.b64decode(body['attachment'][0]['content'])==payload
        assert body['attachment'][0]['name']=='test.txt'
        return Response()
    monkeypatch.setattr(email_service.urllib.request,'urlopen',send)
    result=email_service.send_artifact(path,'test.txt','recipient@example.com')
    assert result['email_delivery']=='accepted_by_provider' and result['message_id']=='<unit-test>'


def test_production_rejects_development_credentials():
    from app.config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None,app_env='production')

def test_production_rejects_case_insensitive_jwt_placeholder():
    from app.config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None,app_env='production',
                 jwt_secret='replace-with-a-random-secret-of-at-least-32-characters',
                 database_url='postgresql+psycopg://u:p@db/xai',cors_origins='https://xai-usg.vercel.app')


def test_production_rejects_unsafe_cors():
    from app.config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None,app_env='production',jwt_secret='a'*48,
                 database_url='postgresql+psycopg://u:p@db/xai',cors_origins='http://localhost:4200')
