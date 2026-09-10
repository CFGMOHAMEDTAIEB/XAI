import json, subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
results={}
for app in ['public_nextjs','web_angular']:
    result=subprocess.run(['npm.cmd','audit','--json'],cwd=root/'apps'/app,capture_output=True,text=True,timeout=180)
    try:
        data=json.loads(result.stdout)
        results[app]={'counts':data.get('metadata',{}).get('vulnerabilities',{}),'packages':{name:{'severity':v['severity'],'direct':v['isDirect'],'fix_available':v['fixAvailable']} for name,v in data.get('vulnerabilities',{}).items()},'registry_audit_available':bool(data.get('metadata'))}
    except ValueError:results[app]={'registry_audit_available':False}
out=root/'docs/development-integration';out.mkdir(exist_ok=True,parents=True)
(out/'npm-audit.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
for name,value in results.items():print(name,json.dumps(value))
