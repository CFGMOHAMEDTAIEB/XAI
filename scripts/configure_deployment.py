"""Propagate real deployed URLs without touching credentials."""
import argparse
from pathlib import Path
from urllib.parse import urlsplit

def origin(value):
    u=urlsplit(value)
    if u.scheme!='https' or not u.hostname or u.hostname in ('localhost','127.0.0.1','10.0.2.2','backend') or u.username or u.password or u.path not in ('','/') or u.query or u.fragment or 'REPLACE_' in value:
        raise argparse.ArgumentTypeError('Provide an actual public HTTPS origin with no credentials/path')
    return value.rstrip('/')

def update(path, changes):
    lines=path.read_text().splitlines();found=set()
    for i,line in enumerate(lines):
        if not line.startswith('#') and '=' in line and line.split('=',1)[0] in changes:
            key=line.split('=',1)[0];lines[i]=key+'='+changes[key];found.add(key)
    for key in changes.keys()-found:lines.append(key+'='+changes[key])
    path.write_text('\n'.join(lines)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['api','public','portal','admin']:p.add_argument('--'+key+'-url',type=origin)
    a=p.parse_args()
    if a.public_url and a.portal_url and a.public_url==a.portal_url:p.error('Public site and portal are separate projects; supply different origins.')
    root=Path(__file__).resolve().parents[1]/'deployment'
    changes={s:{} for s in ['render.api','vercel.public','vercel.portal','render.admin']}
    if a.api_url:
        changes['vercel.public']['INTERNAL_API_URL']=a.api_url
        changes['vercel.portal']['XAI_API_URL']=a.api_url
        changes['render.admin']['PlatformApi__BaseUrl']=a.api_url
    if a.public_url:
        changes['vercel.public']['NEXT_PUBLIC_SITE_URL']=a.public_url
        changes['vercel.portal']['NEXT_PUBLIC_SITE_URL']=a.public_url
        changes['render.api']['PUBLIC_BASE_URL']=a.public_url
    if a.portal_url:
        changes['vercel.public']['NEXT_PUBLIC_APP_URL']=a.portal_url
        changes['render.admin']['PortalUrl']=a.portal_url
    if a.admin_url:changes['vercel.portal']['ADMIN_URL']=a.admin_url
    for name,values in changes.items():
        if values:update(root/('.env.'+name),values)
    # Preserve configured origins not replaced by this invocation; remove placeholders.
    vals={}
    for name in ['vercel.public','vercel.portal']:
        vals.update(dict(line.split('=',1) for line in (root/('.env.'+name)).read_text().splitlines() if '=' in line and not line.startswith('#')))
    cors=[vals.get(k,'') for k in ['NEXT_PUBLIC_SITE_URL','NEXT_PUBLIC_APP_URL','ADMIN_URL']]
    cors=list(dict.fromkeys(v for v in cors if v and 'REPLACE_' not in v))
    if cors:update(root/'.env.render.api',{'CORS_ORIGINS':','.join(cors)})
    print('Updated local deployment URL fields only. Re-import affected environment settings and redeploy. No cloud deployment performed.')
if __name__=='__main__':main()
