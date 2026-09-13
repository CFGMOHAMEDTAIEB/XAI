"""Email diagnostic tests mock all network activity; no messages are sent."""
from pathlib import Path

import email_diagnostics


BASE = """EMAIL_PROVIDER=brevo
BREVO_API_KEY=secret-api-key
BREVO_SENDER_EMAIL=private-sender@example.com
BREVO_SENDER_NAME=XAI Compress
SMTP_TIMEOUT_SECONDS=30
"""


def run(tmp_path: Path, capsys, monkeypatch, extra='', accepted=True):
    env_file = tmp_path / '.env.test'
    env_file.write_text(BASE + extra, encoding='utf-8')
    calls = []
    monkeypatch.setattr(email_diagnostics, '_send_smoke_test',
                        lambda values, recipient: calls.append((values, recipient)) or accepted)
    email_diagnostics.main(['--env-file', str(env_file), '--send-smoke-test'])
    return capsys.readouterr().out, calls


def test_missing_recipient_is_blocked(tmp_path, capsys, monkeypatch):
    output, calls = run(tmp_path, capsys, monkeypatch)
    assert 'MAIL_SEND_ATTEMPT = BLOCKED_NO_DESIGNATED_NONPRODUCTION_MAILBOX' in output
    assert calls == []


def test_provider_rejection(tmp_path, capsys, monkeypatch):
    output, calls = run(tmp_path, capsys, monkeypatch,
                        'XAI_EMAIL_SMOKE_RECIPIENT=private-recipient@example.com\n', accepted=False)
    assert 'MAIL_SEND_ATTEMPT = REJECTED' in output
    assert 'MAILBOX_DELIVERY = MANUAL' in output
    assert len(calls) == 1


def test_accepted_send(tmp_path, capsys, monkeypatch):
    output, calls = run(tmp_path, capsys, monkeypatch,
                        'XAI_EMAIL_SMOKE_RECIPIENT=private-recipient@example.com\n')
    assert 'MAIL_SEND_ATTEMPT = ACCEPTED' in output
    assert 'MAILBOX_DELIVERY = MANUAL' in output
    assert len(calls) == 1


def test_secrets_and_addresses_are_never_printed(tmp_path, capsys, monkeypatch):
    output, _ = run(tmp_path, capsys, monkeypatch,
                    'XAI_EMAIL_SMOKE_RECIPIENT=private-recipient@example.com\n', accepted=False)
    assert 'secret-api-key' not in output
    assert 'private-sender@example.com' not in output
    assert 'private-recipient@example.com' not in output
