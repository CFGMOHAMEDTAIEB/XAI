"""Sanitized API-level local E2E for the two configured development users."""
from __future__ import annotations
import hashlib,json,os,secrets,sys,time,urllib.error,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def env_file(path):
    out={}
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line=raw.strip()
        if line and not line.startswith('#') and '=' in line:
            key,value=line.split('=',1);out[key.strip()]=value.strip()
    return out
CFG=env_file(ROOT/'.env')
if CFG.get('APP_ENV','development')!='development':raise SystemExit('Refusing non-development E2E')
API=CFG.get('PUBLIC_API_URL') or f"http://127.0.0.1:{CFG.get('API_PORT','18000')}"

class Api:
    def __init__(self):self.token=None
    def call(self,route,data=None,upload=None,expected=200):
        headers={};body=None
        if self.token:headers['Authorization']='Bearer '+self.token
        if data is not None:body=json.dumps(data).encode();headers['Content-Type']='application/json'
        if upload is not None:
            name,payload=upload;boundary=secrets.token_hex(20)
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="upload"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+payload+f'\r\n--{boundary}--\r\n'.encode();headers['Content-Type']='multipart/form-data; boundary='+boundary
        req=urllib.request.Request(API.rstrip('/')+route,body,headers,method='POST' if body is not None else 'GET')
        try:
            with urllib.request.urlopen(req,timeout=600) as response:status=response.status;payload=response.read();content=response.headers.get('Content-Type','')
        except urllib.error.HTTPError as exc:status=exc.code;payload=exc.read();content=exc.headers.get('Content-Type','')
        if status!=expected:raise AssertionError(f'{route}: expected HTTP {expected}, got {status}')
        return json.loads(payload) if 'application/json' in content else payload
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    report={'scenario':'API-level E2E (not GUI automation)','environment':'local development','result':'FAIL','checks':{}}
    a,b,anon=Api(),Api(),Api();refresh=[]
    try:
        health=a.call('/health');assert health['status']=='ok';report['checks']['health']='PASS'
        ta=a.call('/auth/login',{'email':CFG['XAI_DEMO_WEB_EMAIL'],'password':CFG['XAI_DEMO_WEB_PASSWORD']});a.token=ta['access_token'];refresh.append(ta['refresh_token'])
        tb=b.call('/auth/login',{'email':CFG['XAI_DEMO_DESKTOP_EMAIL'],'password':CFG['XAI_DEMO_DESKTOP_PASSWORD']});b.token=tb['access_token'];refresh.append(tb['refresh_token']);report['checks']['authentication']='PASS'
        original=(b'XAI-Compress harmless local demonstration fixture.\n'*256)
        started=time.perf_counter();job=a.call('/compression/jobs',upload=('demo.txt',original));elapsed=time.perf_counter()-started
        assert job['integrity_verified'] and job['sha256']==sha(original)
        artifact=a.call(f"/files/{job['id']}/download");restored=a.call('/compression/decompress',upload=('demo.txt.xaic',artifact));assert restored==original
        report['compression']={'original_size':len(original),'compressed_size':len(artifact),'codec':job['codec'],'route':job.get('engine',{}).get('strategy') if isinstance(job.get('engine'),dict) else None,'compression_seconds':elapsed,'original_sha256':sha(original),'decompressed_sha256':sha(restored),'sha256_match':True}
        report['checks']['round_trip']='PASS'
        anon.call(f"/files/{job['id']}/download",expected=401);b.call(f"/files/{job['id']}/download",expected=404);report['checks']['anonymous_and_owner_boundaries']='PASS'
        share=a.call('/shares',{'file_id':job['id'],'recipient_email':CFG['XAI_DEMO_DESKTOP_EMAIL'],'expires_minutes':60,'max_downloads':2});code=share['share_code']
        redeemed=b.call('/shares/redeem',{'code':code});assert redeemed['file']['sha256']==sha(original)
        shared=b.call('/shares/download',{'code':code});assert shared==artifact
        restored_by_b=b.call('/compression/decompress',upload=('shared.xaic',shared));assert restored_by_b==original
        report['checks']['share_recipient_access']='PASS';report['checks']['recipient_round_trip']='PASS';report['result']='PASS'
    finally:
        for client,token in zip((a,b),refresh):
            try:client.call('/auth/logout',{'refresh_token':token})
            except Exception:pass
        out=ROOT/'reports';out.mkdir(exist_ok=True)
        (out/'demo_e2e_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        lines=['# Local XAI-Compress demo E2E','',f"Result: **{report['result']}**",'', 'This is API-level E2E through the same backend contract used by the clients; no GUI automation is claimed.','', '## Checks','']+[f"- {k}: {v}" for k,v in report.get('checks',{}).items()]
        if 'compression' in report:lines+=['','## Compression evidence','']+[f"- {k}: `{v}`" for k,v in report['compression'].items()]
        (out/'demo_e2e_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return 0 if report['result']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
