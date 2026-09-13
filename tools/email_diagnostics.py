"""Secret-safe email diagnostics. Never prints credentials, addresses, or provider bodies."""
import argparse
import urllib.request
from pathlib import Path
from types import SimpleNamespace


def configured(value: str) -> str:
    return 'configured' if value and 'REPLACE_' not in value else 'unconfigured'


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _brevo_connectivity(values: dict[str, str]) -> bool:
    credential = values.get('BREVO_API_KEY', '')
    if values.get('EMAIL_PROVIDER', '').lower() != 'brevo' or configured(credential) == 'unconfigured':
        return False
    request = urllib.request.Request('https://api.brevo.com/v3/account',
        headers={'api-key': credential, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=int(values.get('SMTP_TIMEOUT_SECONDS', '30'))) as response:
            response.read(1)
            return response.status == 200
    except (OSError, ValueError):
        return False


def _send_smoke_test(values: dict[str, str], recipient: str) -> bool:
    # Import the backend transport rather than maintaining a second production sender.
    import sys
    api_root = Path(__file__).resolve().parents[1] / 'services' / 'api_fastapi'
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))
    from app.email_service import VerificationEmailError, send_delivery_smoke_test

    try:
        selected_settings = SimpleNamespace(
            email_provider=values.get('EMAIL_PROVIDER', '').lower(),
            brevo_api_key=values.get('BREVO_API_KEY', ''),
            brevo_sender_email=values.get('BREVO_SENDER_EMAIL', ''),
            brevo_sender_name=values.get('BREVO_SENDER_NAME', 'XAI Compress'),
            smtp_timeout_seconds=int(values.get('SMTP_TIMEOUT_SECONDS', '30')),
        )
        send_delivery_smoke_test(recipient, selected_settings)
        return True
    except (VerificationEmailError, OSError, ValueError):
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--connectivity', action='store_true')
    parser.add_argument('--send-smoke-test', action='store_true')
    args = parser.parse_args(argv)
    values = read_env_file(args.env_file)

    provider = values.get('EMAIL_PROVIDER', '').lower()
    sender = values.get('BREVO_SENDER_EMAIL', '') if provider == 'brevo' else values.get(
        'RESEND_FROM_EMAIL', '') if provider == 'resend' else values.get('SMTP_FROM', '')
    credential = values.get('BREVO_API_KEY', '') if provider == 'brevo' else values.get(
        'RESEND_API_KEY', '') if provider == 'resend' else values.get('SMTP_PASSWORD', '')
    print(f'EMAIL_PROVIDER = {configured(provider)}')
    print(f'SENDER = {configured(sender)}')
    print(f'PROVIDER_CREDENTIAL = {configured(credential)}')

    if args.connectivity:
        print(f'BREVO_API_CONNECTIVITY = {"PASS" if _brevo_connectivity(values) else "FAIL"}')

    recipient = values.get('XAI_EMAIL_SMOKE_RECIPIENT', '')
    if configured(recipient) == 'unconfigured':
        print('MAIL_SEND_ATTEMPT = BLOCKED_NO_DESIGNATED_NONPRODUCTION_MAILBOX')
        return 0
    if not args.send_smoke_test:
        print('MAIL_SEND_ATTEMPT = BLOCKED')
        return 0

    prerequisites_ready = provider == 'brevo' and all(
        configured(value) == 'configured' for value in (sender, credential))
    accepted = prerequisites_ready and _send_smoke_test(values, recipient)
    print(f'MAIL_SEND_ATTEMPT = {"ACCEPTED" if accepted else "REJECTED"}')
    print('MAILBOX_DELIVERY = MANUAL')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
