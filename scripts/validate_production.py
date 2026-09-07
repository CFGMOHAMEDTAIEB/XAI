"""Read-only deployment checks by default. --exercise-files uses real authenticated XAI jobs.
--send-email explicitly opts into the interactive full email/receipt E2E runner.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import urllib.error
import getpass
from test_full_e2e import Api,sha

def request(url,method='GET',headers=None):
    req=urllib.request.Request(url,method=method,headers=headers or {})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:return r.status,dict(r.headers),r.read()
    except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--api',required=True);p.add_argument('--public',required=True);p.add_argument('--portal',required=True)
    p.add_argument('--allow-local',action='store_true');p.add_argument('--exercise-files',action='store_true')
    p.add_argument('--send-email',action='store_true');p.add_argument('--input',type=Path)
    a=p.parse_args();results=[]
    def check(name,fn):
        try:
            if not fn():raise ValueError('Unexpected response')
            results.append({'check':name,'result':'PASS'})
        except Exception as e:results.append({'check':name,'result':'FAIL','reason':str(e)[:200]})
    for value in [a.api,a.public,a.portal]:
        if 'REPLACE_' in value or (not a.allow_local and not value.startswith('https://')):p.error('Supply deployed HTTPS URLs, or --allow-local for diagnostics')
    a.api=a.api.rstrip('/');a.public=a.public.rstrip('/');a.portal=a.portal.rstrip('/')
    check('backend health',lambda:json.loads(request(a.api+'/health')[2])['compression']['selector_v2'] is True)
    def status():
        code,_,body=request(a.api+'/public/status');obj=json.loads(body)
        return code==200 and set(obj)=={'status','services'} and all(x in ('operational','degraded','unavailable','unknown') for x in obj['services'].values())
    check('public status contract',status)
    check('public site reachable and portal link',lambda:a.portal.encode() in request(a.public)[2])
    for path in ['/login','/register','/compress','/inbox','/security','/settings']:
        check('portal direct route '+path,lambda path=path:request(a.portal+path)[0]==200)
    check('public status page',lambda:request(a.public+'/status')[0]==200)
    check('authentication required',lambda:request(a.api+'/auth/me')[0]==401)
    def cors():
        code,headers,_=request(a.api+'/compression/jobs','OPTIONS',{'Origin':a.portal,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type'})
        headers={k.lower():v for k,v in headers.items()}
        return code==200 and headers.get('access-control-allow-origin')==a.portal
    check('allowed portal CORS',cors)
    check('untrusted CORS rejected',lambda:request(a.api+'/compression/jobs','OPTIONS',{'Origin':'https://untrusted.example','Access-Control-Request-Method':'POST'})[0]==400)
    api=Api(a.api)
    for route in ['/compression/jobs','/compression/decompress']:
        def protected(route=route):
            try:api.call(route,upload=('probe.bin',b'probe'))
            except RuntimeError as e:return 'HTTP 401' in str(e)
            return False
        check('protected route '+route,protected)
    if a.exercise_files:
        credentials={'email':input('Enrolled XAI email: '),'password':getpass.getpass('Password: '),'totp_code':getpass.getpass('Mobile TOTP: ')}
        api.token=api.call('/auth/login',credentials)['access_token'];del credentials
        def roundtrip():
            if not api.call('/auth/me')['mfa_enabled']:raise ValueError('MFA enrollment required')
            original=a.input.read_bytes() if a.input else b'XAI deployment integration\n'*4096
            job=api.call('/compression/jobs',upload=('deployment-check.bin',original))
            artifact=api.call(f"/files/{job['id']}/download")
            restored=api.call('/compression/decompress',upload=('deployment-check.bin.xaic',artifact))
            return original==restored and sha(original)==job['sha256']
        check('real authenticated compression/decompression',roundtrip)
        if api.call('/auth/me')['is_admin']:
            check('email configuration (does not send)',lambda:(lambda c:c['configured'] and c['xaic_supported'])(api.call('/admin/email/configuration')))
        else:results.append({'check':'email configuration','result':'NOT VERIFIED','reason':'Admin session required; public status cannot expose credential configuration'})
    else:results.append({'check':'email configuration','result':'NOT VERIFIED','reason':'Use --exercise-files with an administrator; no email is sent'})
    if a.send_email:
        if not a.input:p.error('--send-email requires --input')
        check('full email receipt/integrity',lambda:subprocess.call([sys.executable,str(Path(__file__).with_name('test_full_e2e.py')),'--api',a.api,'--input',str(a.input)])==0)
    out=Path('dist/deployment-validation');out.mkdir(parents=True,exist_ok=True)
    (out/'checks.json').write_text(json.dumps(results,indent=2))
    for result in results:print(result['check']+': '+result['result'])
    return 1 if any(r['result']!='PASS' for r in results) else 0
if __name__=='__main__':sys.exit(main())
