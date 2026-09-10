"""Backend email delivery. Provider acceptance does not prove inbox receipt."""
import base64
import json
import urllib.request
import urllib.error
import hashlib
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid, formataddr
from pathlib import Path

from .config import settings


class VerificationEmailError(OSError):
    """Only fixed, public diagnostics may be supplied to this exception."""


def verification_configuration_missing():
    if settings.email_provider in ('smtp','mailpit'):
        return _smtp_configuration_missing()
    missing = []
    providers = {'resend': ('resend_api_key', 'resend_from_email'),
                 'brevo': ('brevo_api_key', 'brevo_sender_email', 'brevo_sender_name')}
    if settings.email_provider not in providers:
        return ['EMAIL_PROVIDER']
    for name in providers[settings.email_provider]:
        value = getattr(settings, name)
        if not value or 'REPLACE_' in value:
            missing.append(name.upper())
    return missing


def send_verification_code(recipient: str, code: str) -> None:
    """Send only the email challenge, never TOTP material. No provider bodies escape."""
    if verification_configuration_missing():
        raise VerificationEmailError('Verification email is not configured; contact support')
    text = (f'Your XAI Compress MFA verification code is {code}. It expires in at most 10 minutes. '
            'Enter it in the XAI application where you started MFA setup. Never share this code. '
            'If you did not request this, ignore this email.')
    if settings.email_provider in ('smtp','mailpit'):
        message=EmailMessage()
        message['From']=formataddr((settings.smtp_from_name,settings.smtp_from))
        message['To']=recipient
        message['Subject']='XAI Compress MFA verification'
        message['Message-ID']=make_msgid()
        message.set_content(text)
        _send_smtp_message(message)
        return
    if settings.email_provider == 'brevo':
        _send_brevo({'sender': {'email': settings.brevo_sender_email, 'name': settings.brevo_sender_name},
                     'to': [{'email': recipient}], 'subject': 'XAI Compress MFA verification',
                     'textContent': text})
        return
    body = {'from': settings.resend_from_email, 'to': [recipient],
            'subject': 'XAI Authenticator verification',
            'text': text}
    _send_resend(body)


def _send_resend(body: dict) -> str:
    request = urllib.request.Request('https://api.resend.com/emails',
        data=json.dumps(body).encode(), headers={
            'Authorization': 'Bearer ' + settings.resend_api_key,
            'Content-Type': 'application/json', 'User-Agent': 'XAI-Authenticator/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=settings.smtp_timeout_seconds) as response:
            result = json.loads(response.read())
            if response.status not in (200, 201) or not isinstance(result, dict) or not isinstance(result.get('id'), str) or not result['id'].strip():
                raise VerificationEmailError('Email provider did not accept the message; retry later')
            return result['id']
    except urllib.error.HTTPError as error:
        # Examine only to classify Resend's documented testing restriction. Never echo it.
        limited = False
        try:
            limited = error.code == 403 and 'only send testing emails' in error.read(8192).decode(errors='replace')
        finally:
            error.close()
        if limited:
            raise VerificationEmailError('Resend test sender can only email the account owner; configure a verified sender domain') from None
        raise VerificationEmailError('Verification email rejected; check Resend credentials and sender verification') from None
    except (OSError, ValueError):
        raise VerificationEmailError('Verification email unavailable; retry later') from None


def _send_brevo(body: dict) -> str:
    request = urllib.request.Request('https://api.brevo.com/v3/smtp/email',
        data=json.dumps(body).encode(), headers={'api-key': settings.brevo_api_key,
        'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=settings.smtp_timeout_seconds) as response:
            result = json.loads(response.read())
            if (response.status != 201 or not isinstance(result, dict)
                    or not isinstance(result.get('messageId'), str) or not result['messageId'].strip()):
                raise VerificationEmailError('Email provider did not accept the message; retry later')
            return result['messageId']
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()  # Never read or log provider response bodies.
        if status in (401, 403):
            raise VerificationEmailError('Verification email rejected; contact support to check Brevo credentials and sender verification') from None
        if status < 500 and status != 429:
            raise VerificationEmailError('Verification email rejected; contact support to check sender and recipient configuration') from None
        raise VerificationEmailError('Verification email unavailable; retry later') from None
    except VerificationEmailError:
        raise
    except (OSError, ValueError):
        raise VerificationEmailError('Verification email unavailable; retry later') from None


def _smtp_configuration_missing():
    missing=[name.upper() for name in ('smtp_host','smtp_from') if not getattr(settings,name) or 'REPLACE_' in getattr(settings,name)]
    if settings.smtp_username and not settings.smtp_password:missing.append('SMTP_PASSWORD')
    if settings.smtp_security not in ('starttls','ssl','none'):missing.append('SMTP_SECURITY')
    if settings.app_env=='production' and (settings.email_provider=='mailpit' or settings.smtp_security=='none'):missing.append('PRODUCTION_EMAIL_POLICY')
    return missing


def _send_smtp_message(message):
    if _smtp_configuration_missing():
        raise VerificationEmailError('SMTP is not configured; contact support')
    try:
        context=ssl.create_default_context()
        kwargs={'host':settings.smtp_host,'port':settings.smtp_port,'timeout':settings.smtp_timeout_seconds}
        connection=smtplib.SMTP_SSL(context=context,**kwargs) if settings.smtp_security=='ssl' else smtplib.SMTP(**kwargs)
        with connection as smtp:
            if settings.smtp_security=='starttls':
                smtp.ehlo();smtp.starttls(context=context);smtp.ehlo()
            if settings.smtp_username:smtp.login(settings.smtp_username,settings.smtp_password)
            if smtp.send_message(message):raise VerificationEmailError('Email recipient was rejected; retry later')
    except (OSError,smtplib.SMTPException):
        raise VerificationEmailError('SMTP delivery unavailable; retry later') from None


def send_smtp_artifact(path: Path, filename: str, recipient: str) -> dict:
    if _smtp_configuration_missing():raise ValueError('SMTP configuration is incomplete')
    if path.stat().st_size > settings.smtp_max_attachment_bytes:
        raise ValueError('Artifact exceeds SMTP_MAX_ATTACHMENT_BYTES')
    payload = path.read_bytes()
    message = EmailMessage()
    message['From'] = formataddr((settings.smtp_from_name,settings.smtp_from))
    message['To'] = recipient
    message['Subject'] = 'XAI Compress file attachment'
    message['Message-ID'] = make_msgid()
    message.set_content('Attached is an XAI compressed file. Import it in XAI Inbox for validated decompression. '
                        'Treat attachments as untrusted regardless of their sender.\n'
                        f'Attachment SHA-256: {hashlib.sha256(payload).hexdigest()}\n')
    message.add_attachment(payload, maintype='application', subtype='octet-stream', filename=filename)
    _send_smtp_message(message)
    return {'email_delivery': 'accepted_by_smtp', 'message_id': message['Message-ID'],
            'recipient_email': recipient, 'filename': filename, 'size': len(payload),
            'mime_type': 'application/octet-stream', 'sha256': hashlib.sha256(payload).hexdigest()}


def configuration_missing():
    if settings.email_provider == 'resend':
        return verification_configuration_missing()
    if settings.email_provider == 'brevo':
        return verification_configuration_missing()
    if settings.email_provider in ('smtp','mailpit'):
        return _smtp_configuration_missing()
    return ['EMAIL_PROVIDER']


def send_artifact(path: Path, filename: str, recipient: str) -> dict:
    missing = configuration_missing()
    if missing: raise ValueError('Missing email configuration: ' + ', '.join(missing))
    if settings.email_provider in ('smtp','mailpit'): return send_smtp_artifact(path, filename, recipient)
    if settings.email_provider == 'resend':
        if path.stat().st_size > settings.smtp_max_attachment_bytes:
            raise ValueError('Artifact exceeds SMTP_MAX_ATTACHMENT_BYTES')
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        message_id = _send_resend({'from': settings.resend_from_email, 'to': [recipient],
            'subject': 'XAI E2E Compressed Artifact Test',
            'text': 'XAI compressed attachment. Treat it as untrusted and validate before use. SHA-256: ' + digest,
            'attachments': [{'filename': filename, 'content': base64.b64encode(payload).decode('ascii')}]})
        return {'email_delivery': 'accepted_by_provider', 'provider': 'resend', 'message_id': message_id,
                'recipient_email': recipient, 'filename': filename, 'size': len(payload),
                'mime_type': 'application/octet-stream', 'sha256': digest}
    if filename.lower().endswith('.xaic'):
        raise ValueError('Brevo HTTPS attachment allowlist does not support .xaic; provider format support is required. The artifact was not renamed or sent.')
    if path.stat().st_size > settings.smtp_max_attachment_bytes:
        raise ValueError('Artifact exceeds SMTP_MAX_ATTACHMENT_BYTES')
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    body = {'sender': {'email': settings.brevo_sender_email, 'name': settings.brevo_sender_name}, 'to': [{'email': recipient}],
            'subject': 'XAI E2E Compressed Artifact Test',
            'textContent': 'XAI compressed attachment. Treat it as untrusted and validate before use. SHA-256: ' + digest,
            'attachment': [{'name': filename, 'content': base64.b64encode(payload).decode('ascii')}]}
    message_id = _send_brevo(body)
    return {'email_delivery': 'accepted_by_provider', 'provider': 'brevo', 'message_id': message_id,
            'recipient_email': recipient, 'filename': filename, 'size': len(payload),
            'mime_type': 'application/octet-stream', 'sha256': digest}
