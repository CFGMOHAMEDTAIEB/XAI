"""Reproducible source route, action and suspicious-content inventories."""
from pathlib import Path
import csv
import re
import json

root=Path(__file__).resolve().parents[1]
out=root/'docs/product-truth-audit';out.mkdir(parents=True,exist_ok=True)
rows=[]
def add(app,route,purpose,source,auth,file,status='PARTIAL',issues='Live interaction not verified',origin=''):
    rows.append(dict(app=app,route=route,purpose=purpose,data_source=source,auth_required=auth,currently_functional=status,production_url=origin+route if origin else 'Not distributed',issues=issues,source_file=str(file.relative_to(root))))
public=root/'apps/public_nextjs/app'
for p in sorted(public.rglob('page.tsx')):
    route='/'+p.parent.relative_to(public).as_posix().replace('.','')
    source='/public/status' if route=='/status' else '/public/shares/{code}' if route.startswith('/share') else 'Reviewed release manifest' if route=='/downloads' else 'Maintained static source'
    issue={'/download':'Redirect added locally; live 404','/privacy':'Policy draft; operator/contact/retention unresolved','/terms':'Legal draft; not final','/contact':'Support endpoint absent; form disabled','/pricing':'No billing; plans removed','/downloads':'No production artifacts','/status':'Prerequisites only; no history; live API probe timed out','/docs':'Resource overview; no hosted full manuals'}.get(route,'Local source reviewed; live interactions unverified')
    add('Next.js',route,'Home' if route=='/' else p.parent.name,source,'No',p,issues=issue,origin='https://xai-compress.vercel.app')
for route,purpose in [('/robots.txt','Crawler rules'),('/sitemap.xml','Public route discovery'),('/_not-found','Framework not-found fallback')]:
    file=public/('robots.ts' if 'robots' in route else 'sitemap.ts' if 'sitemap' in route else 'layout.tsx')
    add('Next.js',route,purpose,'Static/framework','No',file,origin='https://xai-compress.vercel.app')
angular=root/'apps/web_angular/src/app'
data={'login':'POST /auth/login','register':'POST /auth/register','dashboard':'GET /history','files':'GET /history; GET /files/{id}/download','compress':'POST /compression/jobs','shares':'POST /shares; POST /files/{id}/email','inbox':'POST /shares/redeem; POST /shares/download; POST /compression/decompress','security':'GET /auth/me; mobile setup instructions','settings':'GET /auth/me'}
for p in sorted((angular/'pages').glob('*.page.ts')):
    name=p.name.split('.')[0]
    add('Angular','/'+name,name,data.get(name,'UNVERIFIED'),'No' if name in ['login','register'] else 'Yes',p,origin='https://portal-xai.vercel.app')
for route,purpose in [('/','Redirect to dashboard behind guard'),('/**','Wildcard redirect to root')]:add('Angular',route,purpose,'Router','Guard on root',angular/'app.routes.ts',origin='https://portal-xai.vercel.app')
admin=root/'apps/admin_dotnet'
sources={'/':'/admin/stats; /admin/jobs','/users':'/admin/users','/jobs':'/admin/jobs','/audit':'/admin/audit','/system':'/public/status','/login':'/auth/login then /admin/stats','/incidents':'No endpoint','/quarantine':'No endpoint','/privacy':'Policy draft','/error':'Framework error'}
for p in sorted((admin/'Components/Pages').glob('*.razor')):
    for route in re.findall(r'@page\s+"([^"]+)"',p.read_text(encoding='utf-8-sig')):
        add('Admin .NET',route,p.stem,sources.get(route,'UNVERIFIED'),'Admin API authorization' if route in ['/','/users','/jobs','/audit'] else 'No protected data',p,
            status='NOT_IMPLEMENTED' if route in ['/incidents','/quarantine'] else 'PARTIAL',issues='Reporting unavailable' if route in ['/incidents','/quarantine'] else 'Browser interaction not verified',origin='https://admin-dotnet.onrender.com')
add('Admin .NET','/health','Liveness','Runtime clock and liveness','No',admin/'Program.cs',origin='https://admin-dotnet.onrender.com')
for app,folder in [('Mobile','mobile_authenticator_flutter'),('Desktop','desktop_flutter')]:
    lib=root/'apps'/folder/'lib'
    for p in sorted((lib/'screens').glob('*.dart')):
        name=p.stem.replace('_screen','')
        source='Local secure storage / device authentication / backend enrollment' if app=='Mobile' else 'Local settings/history or configured API and Python engine'
        add(app,name,'Native screen: '+name,source,'Device unlock' if app=='Mobile' else 'Cloud actions require account; local actions do not',p)
    if app=='Mobile':
        for name in ['not_configured','awaiting_email','saving','awaiting_totp','expired','enabled']:
            add(app,'MFA/'+name,'Enrollment state','/auth/totp endpoints + secure storage','Yes',lib/'widgets/mfa_setup.dart')
        add(app,'account/delete-confirmation','Delete local factor; does not disable server MFA','Secure storage','Device unlock',lib/'widgets/account_code_card.dart')
        add(app,'startup-error','Retry storage initialization','Secure storage','No',lib/'main.dart')
    else:add(app,'Account/register-login','Register/login/TOTP/logout; redeem/download/history','FastAPI auth/history/shares','Per action',lib/'screens/receive_screen.dart')
with (out/'routes.csv').open('w',encoding='utf-8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
source_roots=[root/'apps/public_nextjs/app',root/'apps/public_nextjs/components',angular,admin/'Components',admin/'Services',root/'apps/mobile_authenticator_flutter/lib',root/'apps/desktop_flutter/lib']
actions=[];suspects=[]
pattern=re.compile(r'\b(mock|demo|fake|placeholder|sample|dummy|TODO|coming soon|hardcoded|uptime|enterprise|premium|testimonial|trusted|encrypted|production|available|localhost|127\.0\.0\.1|10\.0\.2\.2|example\.com)\b|99\.9',re.I)
for directory in source_roots:
    for p in sorted(directory.rglob('*')):
        if p.suffix not in ['.tsx','.ts','.razor','.cs','.dart']:continue
        text=p.read_text(encoding='utf-8-sig')
        for number,line in enumerate(text.splitlines(),1):
            if pattern.search(line):suspects.append(dict(file=str(p.relative_to(root)),line=number,classification='DEMO' if p.name=='DemoAdminData.cs' else 'UNVERIFIED',text=line[:10000]))
        for m in re.finditer(r'<(?:a|Link|NavLink|button)\b[^>]*>|(?:onPressed|onTap|onSelected)\s*:[^\n]{0,180}',text):
            value=m.group();classification='PLACEHOLDER' if re.search(r'href=["\'](?:#|javascript:)',value) else 'NOT_AVAILABLE' if re.search(r'\bdisabled(?:\s|>)|onPressed:\s*null',value) else 'UNVERIFIED'
            actions.append(dict(file=str(p.relative_to(root)),line=text[:m.start()].count('\n')+1,classification=classification,source=value))
for filename,entries in [('actions.csv',actions),('suspicious-source.csv',suspects)]:
    with (out/filename).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(entries[0]));writer.writeheader();writer.writerows(entries)
endpoints=[]
for p in (root/'services/api_fastapi/app').glob('*.py'):
    for m in re.finditer(r'@app\.(get|post|put|patch|delete)\([\'\"]([^\'\"]+)',p.read_text()):endpoints.append({'method':m.group(1).upper(),'path':m.group(2),'file':str(p.relative_to(root))})
(out/'backend-routes.json').write_text(json.dumps(endpoints,indent=2),encoding='utf-8')
print(f'{len(rows)} routes/screens, {len(actions)} action declarations, {len(suspects)} suspicious source lines, {len(endpoints)} API routes')
import subprocess
scopes=['apps','services','scripts','docs','deployment']
changed=subprocess.check_output(['git','diff','--name-only','--',*scopes],cwd=root,text=True,stderr=subprocess.DEVNULL).splitlines()
new=subprocess.check_output(['git','ls-files','--others','--exclude-standard','--',*scopes],cwd=root,text=True).splitlines()
(out/'modified-files.txt').write_text('\n'.join(sorted(set(changed+new+['docs/product-truth-audit/modified-files.txt'])))+'\n',encoding='utf-8')
