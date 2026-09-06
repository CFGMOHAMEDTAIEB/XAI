"""Focused unit tests; SMTP transport is mocked only here, never in live E2E."""
import hashlib
import smtplib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app import email_service
from app.config import settings
from app.main import app, current_user, safe_upload_name


def test_smtp_missing_configuration_does_not_connect(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'smtp_host', '')
    monkeypatch.setattr(settings, 'smtp_from', '')
    def unexpected(**kwargs):
        pytest.fail('SMTP must not connect without configuration')
    monkeypatch.setattr(smtplib, 'SMTP', unexpected)
    with pytest.raises(ValueError, match='SMTP_HOST, SMTP_FROM'):
        email_service.send_artifact(tmp_path/'missing.xaic', 'file.xaic', 'receiver@example.com')


def test_smtp_attachment_preserves_bytes_and_requires_tls(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'smtp_host', 'smtp.example.com')
    monkeypatch.setattr(settings, 'smtp_from', 'sender@example.com')
    monkeypatch.setattr(settings, 'smtp_security', 'starttls')
    monkeypatch.setattr(settings, 'smtp_username', '')
    payload = b'XAIC\x06\x00\xff\r\n' * 30
    path = tmp_path/'artifact.xaic'; path.write_bytes(payload)
    captured = {}
    class Transport:
        def __init__(self, **kwargs): captured['timeout'] = kwargs['timeout']
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ehlo(self): pass
        def starttls(self, context): captured['tls'] = context.check_hostname
        def send_message(self, message): captured['message'] = message; return {}
    monkeypatch.setattr(smtplib, 'SMTP', Transport)
    result = email_service.send_artifact(path, 'original.bin.xaic', 'receiver@example.com')
    attachment = list(captured['message'].iter_attachments())[0]
    assert captured['message']['Subject'] == 'XAI E2E Compressed Artifact Test'
    assert captured['tls'] and captured['timeout'] > 0
    assert attachment.get_payload(decode=True) == payload
    assert attachment.get_filename() == 'original.bin.xaic'
    assert attachment.get_content_type() == 'application/octet-stream'
    assert result['sha256'] == hashlib.sha256(payload).hexdigest()
    assert result['email_delivery'] == 'accepted_by_smtp'


@pytest.mark.parametrize('name', ['../input.xaic', r'C:\temp\input.xaic', '..', '\r\n'])
def test_upload_names_cannot_select_storage_paths(name):
    cleaned = safe_upload_name(name)
    assert cleaned and '/' not in cleaned and '\\' not in cleaned and cleaned not in ('.', '..')


def test_untrusted_upload_size_limit_and_cleanup(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'storage_path', str(tmp_path))
    monkeypatch.setattr(settings, 'max_upload_bytes', 8)
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=123)
    try:
        response = TestClient(app).post('/compression/decompress', files={'upload': ('input.xaic', b'X'*9)})
        assert response.status_code == 413
        assert list((tmp_path/'123').iterdir()) == []
        response = TestClient(app).post('/compression/decompress', files={'upload': ('input.xaic', b'fake')})
        assert response.status_code == 400
        assert list((tmp_path/'123').iterdir()) == []
    finally:
        app.dependency_overrides.clear()


def test_compression_upload_limit_cleans_closed_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'storage_path', str(tmp_path))
    monkeypatch.setattr(settings, 'max_upload_bytes', 8)
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=123)
    try:
        response = TestClient(app).post('/compression/jobs', files={'upload': ('../input.bin', b'X'*9)})
        assert response.status_code == 413
        assert list((tmp_path/'123').iterdir()) == []
    finally:
        app.dependency_overrides.clear()
