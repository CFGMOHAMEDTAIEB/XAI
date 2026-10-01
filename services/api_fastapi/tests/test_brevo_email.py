"""Brevo transport is mocked: these checks never send a real email."""
import io
import json
import urllib.error
from datetime import datetime
import pytest
from app import email_service
from app.config import settings, Settings

@pytest.fixture(autouse=True)
def provider(monkeypatch):
    monkeypatch.setattr(settings, 'email_provider', 'brevo')
    monkeypatch.setattr(settings, 'brevo_api_key', 'unit-test-placeholder')
    monkeypatch.setattr(settings, 'brevo_sender_email', 'sender@example.com')
    monkeypatch.setattr(settings, 'brevo_sender_name', 'XAI Compress')

class Reply:
    status = 201
    payload = b'{"messageId":"<unit-test>"}'
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.payload

def test_verification_contract(monkeypatch):
    def send(request, timeout):
        assert request.full_url == 'https://api.brevo.com/v3/smtp/email'
        assert request.get_method() == 'POST'
        assert request.get_header('Api-key') == settings.brevo_api_key
        assert timeout == settings.smtp_timeout_seconds
        body = json.loads(request.data)
        assert set(body) == {'sender', 'to', 'subject', 'textContent'}
        assert body['sender'] == {'email': 'sender@example.com', 'name': 'XAI Compress'}
        assert body['to'] == [{'email': 'registered@example.com'}]
        assert '123456' in body['textContent']
        assert '10 minutes' in body['textContent'] and 'Never share' in body['textContent']
        assert settings.brevo_api_key not in str(body)
        return Reply()
    monkeypatch.setattr(email_service.urllib.request, 'urlopen', send)
    email_service.send_verification_code('registered@example.com', '123456')

@pytest.mark.parametrize('purpose,expected_subject',[
    ('ACCOUNT_EMAIL_VERIFY','Verify your XAICD account'),
    ('PASSWORD_RESET','Reset your XAICD password'),
    ('PASSWORD_RESET_SUCCESS','Your XAICD password was changed')])
def test_account_email_templates_are_accepted_without_secret_leak(monkeypatch,purpose,expected_subject):
    captured=[]
    monkeypatch.setattr(email_service,'_send_brevo',lambda body:captured.append(body) or '<unit-test>')
    email_service.send_account_email('registered@example.com',None if purpose.endswith('SUCCESS') else '123456',purpose)
    assert captured[0]['subject']==expected_subject
    assert 'textContent' in captured[0] and 'htmlContent' in captured[0]
    assert 'http://' not in captured[0]['htmlContent'] and 'https://' not in captured[0]['htmlContent']
    assert settings.brevo_api_key not in str(captured[0])

@pytest.mark.parametrize('status', [400,401,403,404,422,429,500,503])
def test_http_errors_are_sanitized(monkeypatch, status, caplog):
    def send(*args, **kwargs):
        raise urllib.error.HTTPError('https://api.brevo.com', status, 'private-provider-detail', {}, io.BytesIO(b'private-provider-detail'))
    monkeypatch.setattr(email_service.urllib.request, 'urlopen', send)
    with pytest.raises(email_service.VerificationEmailError) as exc:
        email_service.send_verification_code('registered@example.com', '123456')
    assert 'private-provider-detail' not in str(exc.value) + caplog.text
    assert '123456' not in str(exc.value) + caplog.text

@pytest.mark.parametrize('payload', [b'null', b'[]', b'{}', b'bad-json', b'{"messageId":null}', b'{"messageId":""}'])
def test_malformed_acceptance_fails_closed(monkeypatch, payload):
    reply = Reply()
    reply.payload = payload
    monkeypatch.setattr(email_service.urllib.request, 'urlopen', lambda *a, **k: reply)
    with pytest.raises(email_service.VerificationEmailError):
        email_service.send_verification_code('registered@example.com', '123456')

@pytest.mark.parametrize('error', [TimeoutError('private'), urllib.error.URLError('private'), ConnectionError('private')])
def test_network_failure(monkeypatch, error):
    def send(*args, **kwargs): raise error
    monkeypatch.setattr(email_service.urllib.request, 'urlopen', send)
    with pytest.raises(email_service.VerificationEmailError, match='unavailable'):
        email_service.send_verification_code('registered@example.com', '123456')

def test_missing_sender_does_not_send(monkeypatch):
    monkeypatch.setattr(settings, 'brevo_sender_email', '')
    monkeypatch.setattr(email_service.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('unexpected network call'))
    assert 'BREVO_SENDER_EMAIL' in email_service.verification_configuration_missing()
    with pytest.raises(email_service.VerificationEmailError, match='not configured'):
        email_service.send_verification_code('registered@example.com', '123456')

def test_missing_key_does_not_send(monkeypatch):
    monkeypatch.setattr(settings, 'brevo_api_key', '')
    monkeypatch.setattr(email_service.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('unexpected network call'))
    assert 'BREVO_API_KEY' in email_service.verification_configuration_missing()
    with pytest.raises(email_service.VerificationEmailError, match='not configured'):
        email_service.send_verification_code('registered@example.com', '123456')

def test_delivery_smoke_test_uses_brevo_transport_without_attachments(monkeypatch):
    captured=[]
    monkeypatch.setattr(email_service, '_send_brevo',
                        lambda body, email_settings=settings: captured.append(body) or '<unit-test>')
    email_service.send_delivery_smoke_test('diagnostic@example.com')
    assert captured[0]['subject'] == 'XAICD email delivery smoke test'
    assert 'XAICD email delivery smoke test' in captured[0]['textContent']
    assert 'attachment' not in captured[0]

def test_share_notification_is_recipient_bound_and_professional(monkeypatch):
    captured=[]
    monkeypatch.setattr(email_service,'_send_brevo',lambda body:captured.append(body) or '<unit-test>')
    expires=datetime(2026,10,1,18,30)
    result=email_service.send_share_notification('recipient@example.com','quarterly-report.xaic','XC-SAFE-CODE',expires,'Test Sender')
    assert result=='accepted_by_provider'
    message=captured[0]
    assert message['to']==[{'email':'recipient@example.com'}]
    assert message['subject']=='XAICD — You received a secure file'
    assert 'quarterly-report.xaic' in message['textContent']
    assert 'Test Sender' in message['textContent']
    assert 'XC-SAFE-CODE' in message['textContent'] and '01 Oct 2026 at 18:30 UTC' in message['textContent']
    assert 'Receive a file' in message['textContent']
    assert 'Do not share it with anyone else' in message['textContent']
    assert 'password' not in message['textContent'].lower()

def test_invalid_configuration():
    with pytest.raises(ValueError, match='EMAIL_PROVIDER'):
        Settings(_env_file=None, email_provider='unknown')
    with pytest.raises(ValueError, match='SMTP_TIMEOUT_SECONDS'):
        Settings(_env_file=None, smtp_timeout_seconds=0)
