"""Real isolated Docker/PostgreSQL/Mailpit/ClamAV/YARA E2E; never targets production."""
from pathlib import Path
import os
import sys
import secrets
import time
import re
import json
import subprocess
import hashlib
import httpx
import pyotp
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
config=dotenv_values(root/'.env.admin-test')
if config.get('APP_ENV')!='development':raise SystemExit('Local development configuration required')
api=httpx.Client(base_url='http://127.0.0.1:18000',timeout=120)
mail=httpx.Client(base_url='http://127.0.0.1:18025',timeout=10)
compose=['docker','compose','--env-file',str(root/'.env.admin-test'),'-f',str(root/'compose.devtest.yml'),'-p','xai-devtest']
results={}
def checked(response,status=200):
    if response.status_code!=status:raise AssertionError(f'Unexpected HTTP status {response.status_code}; expected {status}')
    return response
def body(response,status=200):return checked(response,status).json()
def email_for(recipient,exclude=()):
    for _ in range(30):
        messages=body(mail.get('/api/v1/messages'))['messages']
        for message in messages:
            if message['ID'] not in exclude and any(x.get('Address')==recipient for x in message.get('To',[])):
                detail=body(mail.get('/api/v1/message/'+message['ID']))
                match=re.search(r'\b[0-9]{6}\b',detail['Text'])
                if not match:raise AssertionError('Verification code missing in captured local email')
                return message['ID'],match.group(),detail['Text']
        time.sleep(1)
    raise AssertionError('Local Mailpit receipt timed out')
def sql(command):
    # This fixed project/database is created exclusively by compose.devtest.yml.
    subprocess.run(compose+['exec','-T','db','psql','-U','xai_devtest','-d','xai_devtest','-v','ON_ERROR_STOP=1'],input=command,text=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)

try:
    token=body(api.post('/auth/login',json={'email':config['XAI_SEED_ADMIN_EMAIL'],'password':config['XAI_SEED_ADMIN_PASSWORD']}))
    admin={'Authorization':'Bearer '+token['access_token']}
    body(api.get('/admin/stats',headers=admin));results['TEST ADMIN LOGIN']='PASS'
    scanner=body(api.get('/admin/security/scanner',headers=admin))
    if scanner['clamav']!='operational' or scanner['yara']!='operational':raise AssertionError('Real scanners are not operational')
    results['CLAMAV']='PASS';results['YARA']='PASS'
    provider=body(api.get('/admin/email/configuration',headers=admin))
    if provider['provider']!='mailpit' or not provider['development_only']:raise AssertionError('Refusing E2E with a real delivery provider')
    email='flow-'+secrets.token_hex(8)+'@example.com';password=secrets.token_urlsafe(32)
    user_tokens=body(api.post('/auth/register',json={'email':email,'password':password}))
    headers={'Authorization':'Bearer '+user_tokens['access_token']}
    checked(api.get('/admin/stats'),401);checked(api.get('/admin/stats',headers=headers),403)
    users=body(api.get('/admin/users',headers=admin));uid=next(u['id'] for u in users if u['email']==email)
    details=body(api.get(f'/admin/users/{uid}',headers=admin));assert not details['mfaEnabled']
    results['ADMIN AUTHORIZATION']='PASS';results['DATABASE']='PASS'
    enrollment=body(api.post('/auth/totp/enroll',headers=headers,json={}))
    eid=enrollment['enrollment_id'];message_id,code,email_text=email_for(email)
    results['MAILPIT']='PASS'
    checked(api.post('/auth/totp/resend',headers=headers,json={}),429)
    wrong=f'{(int(code)+1)%1000000:06d}'
    checked(api.post('/auth/totp/email/confirm',headers=headers,json={'enrollment_id':eid,'code':wrong}),400)
    sql(f"UPDATE totp_enrollments SET code_expires_at=NOW()-INTERVAL '1 minute' WHERE user_id={int(uid)};")
    checked(api.post('/auth/totp/email/confirm',headers=headers,json={'enrollment_id':eid,'code':code}),410)
    sql(f"UPDATE totp_enrollments SET last_sent_at=NOW()-INTERVAL '2 minutes' WHERE user_id={int(uid)};")
    body(api.post('/auth/totp/resend',headers=headers,json={}))
    _,code,email_text=email_for(email,[message_id])
    disclosure=body(api.post('/auth/totp/email/confirm',headers=headers,json={'enrollment_id':eid,'code':code}))
    assert disclosure['secret'] not in email_text
    checked(api.post('/auth/totp/email/confirm',headers=headers,json={'enrollment_id':eid,'code':code}),409)
    body(api.post('/auth/totp/confirm',headers=headers,json={'enrollment_id':eid,'code':pyotp.TOTP(disclosure['secret']).now()}))
    checked(api.post('/auth/login',json={'email':email,'password':password}),401)
    login=body(api.post('/auth/login',json={'email':email,'password':password,'totp_code':pyotp.TOTP(disclosure['secret']).now()}))
    results['MFA EMAIL']='PASS';results['MFA TOTP']='PASS'
    headers={'Authorization':'Bearer '+login['access_token']}
    original=b'XAI harmless local integration fixture\n'*256
    job=body(api.post('/compression/jobs',headers=headers,files={'upload':('integration.txt',original)}))
    artifact=checked(api.get(f"/files/{job['id']}/download",headers=headers)).content
    restored=checked(api.post('/compression/decompress',headers=headers,files={'upload':('integration.xaic',artifact)})).content
    assert original==restored and hashlib.sha256(original).hexdigest()==job['sha256']
    results['CLEAN COMPRESSION']='PASS'
    subprocess.run(compose+['stop','clamav'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    try:checked(api.post('/compression/jobs',headers=headers,files={'upload':('blocked.txt',b'harmless')}),503)
    finally:subprocess.run(compose+['start','clamav'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    results['FAIL-CLOSED']='PASS'
    body(api.post('/auth/logout',json={'refresh_token':login['refresh_token']}))
    checked(api.post('/auth/refresh',json={'refresh_token':login['refresh_token']}),401)
    # Exercise the independently selected generic SMTP transport against Mailpit.
    os.environ['APP_ENV']='development'
    sys.path.insert(0,str(root/'services/api_fastapi'))
    from app.config import settings
    from app.email_service import send_verification_code
    settings.email_provider='smtp';settings.smtp_host='127.0.0.1';settings.smtp_port=11025
    settings.smtp_security='none';settings.smtp_username='';settings.smtp_from=config['SMTP_FROM']
    recipient='smtp-'+secrets.token_hex(8)+'@example.com';challenge=f'{secrets.randbelow(1000000):06d}'
    send_verification_code(recipient,challenge)
    _,received,_=email_for(recipient);assert received==challenge
    results['SMTP']='PASS'
except Exception as error:
    results['INCOMPLETE']='FAIL: '+type(error).__name__
finally:
    out=root/'docs/development-integration';out.mkdir(parents=True,exist_ok=True)
    (out/'local-security-e2e.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    for name,result in results.items():print(name+' = '+result)
    api.close();mail.close()
if 'INCOMPLETE' in results:raise SystemExit(1)
