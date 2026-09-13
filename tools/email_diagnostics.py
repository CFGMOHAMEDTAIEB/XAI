"""Secret-safe email diagnostics. Never prints credentials, recipients, or provider bodies."""
import argparse
import os
import urllib.error
import urllib.request
from pathlib import Path

def configured(value: str) -> str:
    return 'configured' if value and 'REPLACE_' not in value else 'unconfigured'


parser=argparse.ArgumentParser()
parser.add_argument('--env-file',type=Path,required=True)
parser.add_argument('--connectivity',action='store_true')
args=parser.parse_args()
values={}
for raw in args.env_file.read_text(encoding='utf-8-sig').splitlines():
    line=raw.strip()
    if not line or line.startswith('#') or '=' not in line:continue
    key,value=line.split('=',1);values[key.strip()]=value.strip().strip('"').strip("'")
provider=values.get('EMAIL_PROVIDER','')
sender=values.get('BREVO_SENDER_EMAIL','') if provider=='brevo' else values.get('RESEND_FROM_EMAIL','') if provider=='resend' else values.get('SMTP_FROM','')
credential=values.get('BREVO_API_KEY','') if provider=='brevo' else values.get('RESEND_API_KEY','') if provider=='resend' else values.get('SMTP_PASSWORD','')
print(f'EMAIL_PROVIDER = {configured(provider)}')
print(f'SENDER = {configured(sender)}')
print(f'PROVIDER_CREDENTIAL = {configured(credential)}')

if not args.connectivity:
    print('PROVIDER_CONNECTIVITY = NOT_ATTEMPTED')
elif provider!='brevo' or configured(credential)=='unconfigured':
    print('BREVO_API_CONNECTIVITY = BLOCKED')
else:
    request=urllib.request.Request('https://api.brevo.com/v3/account',headers={'api-key':credential,'Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=int(values.get('SMTP_TIMEOUT_SECONDS','30'))) as response:
            response.read(1)
            print('BREVO_API_CONNECTIVITY = PASS' if response.status==200 else 'BREVO_API_CONNECTIVITY = FAIL')
    except urllib.error.HTTPError as error:
        print(f'BREVO_API_CONNECTIVITY = FAIL_HTTP_{error.code}')
        error.close()
    except OSError:
        print('BREVO_API_CONNECTIVITY = FAIL_NETWORK')

print('MAIL_SEND_ATTEMPT = BLOCKED_NO_DESIGNATED_NONPRODUCTION_MAILBOX' if not os.getenv('XAI_EMAIL_SMOKE_RECIPIENT') else 'MAIL_SEND_ATTEMPT = AVAILABLE_NOT_REQUESTED')
