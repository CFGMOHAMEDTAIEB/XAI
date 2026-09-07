"""SMTP attachment delivery. A successful return means provider acceptance, not receipt."""
import base64
import json
import urllib.request
import urllib.error
import hashlib
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from .config import settings


def send_smtp_artifact(path: Path, filename: str, recipient: str) -> dict:
    missing = [name for name in ('smtp_host', 'smtp_from') if not getattr(settings, name)]
    if settings.smtp_username and not settings.smtp_password:
        missing.append('smtp_password')
    if missing:
        raise ValueError('Missing email configuration: ' + ', '.join(n.upper() for n in missing))
    if settings.smtp_security not in ('starttls', 'ssl'):
        raise ValueError('SMTP_SECURITY must be starttls or ssl')
    if path.stat().st_size > settings.smtp_max_attachment_bytes:
        raise ValueError('Artifact exceeds SMTP_MAX_ATTACHMENT_BYTES')
    payload = path.read_bytes()
    message = EmailMessage()
    message['From'] = settings.smtp_from
    message['To'] = recipient
    message['Subject'] = 'XAI E2E Compressed Artifact Test'
    message['Message-ID'] = make_msgid()
    message.set_content('Attached is an XAI compressed file. Import it in XAI Inbox for validated decompression. '
                        'Treat attachments as untrusted regardless of their sender.\n'
                        f'Attachment SHA-256: {hashlib.sha256(payload).hexdigest()}\n')
    message.add_attachment(payload, maintype='application', subtype='octet-stream', filename=filename)
    context = ssl.create_default_context()
    kwargs = {'host': settings.smtp_host, 'port': settings.smtp_port, 'timeout': settings.smtp_timeout_seconds}
    connection = (smtplib.SMTP_SSL(context=context, **kwargs) if settings.smtp_security == 'ssl'
                  else smtplib.SMTP(**kwargs))
    with connection as smtp:
        if settings.smtp_security == 'starttls':
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        refused = smtp.send_message(message)
        if refused:
            raise smtplib.SMTPException('Recipient rejected')
    return {'email_delivery': 'accepted_by_smtp', 'message_id': message['Message-ID'],
            'recipient_email': recipient, 'filename': filename, 'size': len(payload),
            'mime_type': 'application/octet-stream', 'sha256': hashlib.sha256(payload).hexdigest()}


def configuration_missing():
    def present(value):
        return bool(value and 'REPLACE_' not in value)
    if settings.email_provider == 'brevo':
        return [key for key, value in [('BREVO_API_KEY', settings.brevo_api_key), ('SMTP_FROM', settings.smtp_from)] if not present(value)]
    if settings.email_provider == 'smtp':
        result = [key for key, value in [('SMTP_HOST', settings.smtp_host), ('SMTP_FROM', settings.smtp_from)] if not present(value)]
        if settings.smtp_username and not present(settings.smtp_password): result.append('SMTP_PASSWORD')
        if settings.smtp_security not in ('starttls', 'ssl'): result.append('SMTP_SECURITY')
        return result
    return ['EMAIL_PROVIDER']


def send_artifact(path: Path, filename: str, recipient: str) -> dict:
    missing = configuration_missing()
    if missing: raise ValueError('Missing email configuration: ' + ', '.join(missing))
    if settings.email_provider == 'smtp': return send_smtp_artifact(path, filename, recipient)
    if filename.lower().endswith('.xaic'):
        raise ValueError('Brevo HTTPS attachment allowlist does not support .xaic; provider format support is required. The artifact was not renamed or sent.')
    if path.stat().st_size > settings.smtp_max_attachment_bytes:
        raise ValueError('Artifact exceeds SMTP_MAX_ATTACHMENT_BYTES')
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    body = {'sender': {'email': settings.smtp_from}, 'to': [{'email': recipient}],
            'subject': 'XAI E2E Compressed Artifact Test',
            'textContent': 'XAI compressed attachment. Treat it as untrusted and validate before use. SHA-256: ' + digest,
            'attachment': [{'name': filename, 'content': base64.b64encode(payload).decode('ascii')}]}
    request = urllib.request.Request('https://api.brevo.com/v3/smtp/email', data=json.dumps(body).encode(),
                                    headers={'api-key': settings.brevo_api_key, 'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=settings.smtp_timeout_seconds) as response:
            result = json.loads(response.read())
            if response.status != 201 or not isinstance(result.get('messageId'), str):
                raise OSError('Brevo did not acknowledge a message ID')
    except (urllib.error.URLError, ValueError):
        # Provider response bodies may contain account details; never expose them.
        raise OSError('Brevo submission failed; check credentials, sender verification and provider availability') from None
    return {'email_delivery': 'accepted_by_provider', 'provider': 'brevo', 'message_id': result['messageId'],
            'recipient_email': recipient, 'filename': filename, 'size': len(payload),
            'mime_type': 'application/octet-stream', 'sha256': digest}
