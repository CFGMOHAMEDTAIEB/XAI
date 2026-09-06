"""SMTP attachment delivery. A successful return means provider acceptance, not receipt."""
import hashlib
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from .config import settings


def send_artifact(path: Path, filename: str, recipient: str) -> dict:
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
