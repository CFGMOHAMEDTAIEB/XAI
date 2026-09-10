import secrets
import ssl
import pytest
from app import email_service
from app.config import settings

@pytest.mark.parametrize('provider,security',[('smtp','starttls'),('smtp','ssl'),('mailpit','none')])
def test_mfa_email_transport(provider,security,monkeypatch,caplog):
    for name,value in dict(app_env='development',email_provider=provider,smtp_host='mailpit',smtp_port=1025,smtp_from='sender@example.com',smtp_username='',smtp_security=security).items():monkeypatch.setattr(settings,name,value)
    captured={}
    class Transport:
        def __init__(self,**kwargs):captured.update(kwargs)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def ehlo(self):pass
        def starttls(self,context):captured['context']=context
        def send_message(self,message):captured['message']=message;return {}
    monkeypatch.setattr(email_service.smtplib,'SMTP',Transport)
    monkeypatch.setattr(email_service.smtplib,'SMTP_SSL',Transport)
    code=f'{secrets.randbelow(1000000):06d}'
    email_service.send_verification_code('recipient@example.com',code)
    assert code in captured['message'].get_content()
    assert 'ignore this email' in captured['message'].get_content()
    assert code not in caplog.text
    assert captured['timeout']>0
    if security!='none':assert captured['context'].check_hostname and captured['context'].verify_mode==ssl.CERT_REQUIRED

def test_no_smtp_fallback_from_brevo(monkeypatch):
    monkeypatch.setattr(settings,'email_provider','brevo');monkeypatch.setattr(settings,'brevo_api_key','')
    monkeypatch.setattr(email_service.smtplib,'SMTP',lambda **kw:pytest.fail('Unselected SMTP fallback'))
    with pytest.raises(email_service.VerificationEmailError):email_service.send_verification_code('person@example.com',str(secrets.randbelow(1000000)))

def test_smtp_failures_are_sanitized(monkeypatch,caplog):
    for name,value in dict(email_provider='smtp',smtp_host='mailpit',smtp_from='sender@example.com',smtp_security='starttls',smtp_username='').items():monkeypatch.setattr(settings,name,value)
    def fail(**kwargs):raise OSError('private-transport-diagnostic')
    monkeypatch.setattr(email_service.smtplib,'SMTP',fail)
    with pytest.raises(email_service.VerificationEmailError) as error:email_service.send_verification_code('person@example.com',str(secrets.randbelow(1000000)))
    assert 'private-transport-diagnostic' not in str(error.value)+caplog.text
