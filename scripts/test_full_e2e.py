"""Real HTTP/SMTP/manual mailbox E2E. No mocked services or locally generated TOTP.

Run with Python 3.11+: python scripts/test_full_e2e.py --input path/to/file
First register/enroll a test account using the API and portal Security screen.
Credentials and mobile codes are prompted without echo. Save the received email as .eml.
"""
import argparse
from email import policy
from email.parser import BytesParser
import getpass
import hashlib
import json
from pathlib import Path
import secrets
import sys
import urllib.error
import urllib.request


class Api:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.token = None

    def call(self, route, data=None, upload=None, method=None):
        headers = {}
        body = None
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        if data is not None:
            body = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        if upload is not None:
            name, payload = upload
            boundary = secrets.token_hex(24)
            name = name.replace('"', '_').replace('\r', '').replace('\n', '')
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="upload"; filename="{name}"\r\n'
                    'Content-Type: application/octet-stream\r\n\r\n').encode() + payload + f'\r\n--{boundary}--\r\n'.encode()
            headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
        req = urllib.request.Request(self.base + route, body, headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                result = response.read()
                return json.loads(result) if 'application/json' in response.headers.get('Content-Type', '') else result
        except urllib.error.HTTPError as exc:
            # Never include request headers, tokens, passwords or TOTP query parameters.
            detail = exc.read().decode(errors='replace')[:500]
            raise RuntimeError(f'HTTP {exc.code}: {detail}') from None


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def received_attachment(eml_path, delivery, expected):
    message = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
    if message.get('Message-ID') != delivery['message_id']:
        raise ValueError('Received message ID does not match SMTP submission')
    # These headers are evidence from a mailbox export, not cryptographic sender trust.
    if not message.get_all('Received'):
        raise ValueError('Mailbox export has no Received headers')
    matches = [part for part in message.walk() if part.get_filename() == delivery['filename']]
    if len(matches) != 1:
        raise ValueError('Expected exactly one matching attachment')
    part = matches[0]
    payload = part.get_payload(decode=True)
    if part.get_content_type() != 'application/octet-stream':
        raise ValueError('Unexpected attachment MIME type')
    if payload != expected or sha(payload) != delivery['sha256']:
        raise ValueError('Received attachment differs from sent artifact')
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--api', default='http://localhost:4200/api', help='Uses the real portal nginx proxy by default')
    parser.add_argument('--recipient', default='m.taieb2k@gmail.com')
    parser.add_argument('--output', type=Path, default=Path('dist/full-e2e'))
    parser.add_argument('--expected-artifact', type=Path,
                        help='Require downloaded artifact to match these exact bytes before sending')
    args = parser.parse_args()
    stage = 'health'
    report = {'result': 'FAIL', 'api': args.api}
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        api = Api(args.api)
        require(api.call('/health')['compression']['selector_v2'], 'Selector model unavailable')
        stage = 'mobile authentication'
        email = input('Enrolled XAI account email: ').strip()
        password = getpass.getpass('XAI password: ')
        code = getpass.getpass('Current code displayed by XAI mobile authenticator: ')
        api.token = api.call('/auth/login', {'email': email, 'password': password, 'totp_code': code})['access_token']
        del password, code
        require(api.call('/auth/me')['mfa_enabled'], 'Account must have mobile TOTP enabled')
        stage = 'upload/compression'
        original = args.input.read_bytes()
        job = api.call('/compression/jobs', upload=(args.input.name, original))
        require(job['integrity_verified'] and job['sha256'] == sha(original), 'Compression integrity check failed')
        artifact = api.call(f"/files/{job['id']}/download")
        require(artifact[:4] == b'XAIC' and len(artifact) == job['compressed_size'], 'Artifact format or size mismatch')
        report.update(original_filename=args.input.name, original_size=len(original), compressed_size=len(artifact),
                      original_sha256=sha(original), artifact_sha256=sha(artifact),
                      compression_ratio=len(original)/len(artifact))
        if args.expected_artifact:
            require(artifact == args.expected_artifact.read_bytes(), 'Artifact differs from approved artifact; email not sent')
        (args.output / (args.input.name + '.xaic')).write_bytes(artifact)
        print('ATTACHMENT_SHA256=' + sha(artifact))
        # Preserve pre-send evidence even if delivery is interrupted or rejected.
        (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        stage = 'email sending'
        delivery = api.call(f"/files/{job['id']}/email", {'recipient_email': args.recipient})
        require(delivery['email_delivery'] in ('accepted_by_smtp', 'accepted_by_provider'), 'Email provider did not accept message')
        require(delivery['sha256'] == sha(artifact), 'SMTP attachment hash mismatch')
        report['email'] = delivery
        stage = 'email receipt/import'
        print('In the recipient mailbox, save the received message as .eml. Do not construct a message locally.')
        eml = Path(input('Path to the actual received .eml: ').strip().strip('"'))
        received = received_attachment(eml, delivery, artifact)
        # No sender allowlist is consulted: every imported attachment is untrusted.
        stage = 'decompression'
        restored = api.call('/compression/decompress', upload=(delivery['filename'], received))
        restored_path = args.output / ('restored-' + args.input.name)
        restored_path.write_bytes(restored)
        report['decompressed_sha256'] = sha(restored)
        report['decompressed_size'] = len(restored)
        stage = 'binary integrity'
        require(restored == original, 'Restored bytes differ from original')
        stage = 'application UI validation'
        print('Also perform portal upload, mobile-code login, and Inbox attachment import in the application UI.')
        require(input('Type UI VERIFIED after those real UI operations succeed: ').strip() == 'UI VERIFIED', 'UI workflow unverified')
        report['result'] = 'PASS'
        print('ORIGINAL_SHA256=' + sha(original))
        print('DECOMPRESSED_SHA256=' + sha(restored))
        print('XAI E2E TEST: PASS')
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        report.update(failing_stage=stage, reason=str(exc) or type(exc).__name__)
        print(f'XAI E2E TEST: FAIL — {stage}: {report["reason"]}')
        return 1
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    sys.exit(main())
