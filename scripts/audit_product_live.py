"""Read-only public production probes; never sends credentials or email."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import json
import urllib.request
import urllib.error

root=Path(__file__).resolve().parents[1]
out=root/'docs/product-truth-audit'
out.mkdir(parents=True,exist_ok=True)
routes=['/'+str(p.parent.relative_to(root/'apps/public_nextjs/app')).replace('\\','/').replace('.','') for p in (root/'apps/public_nextjs/app').rglob('page.tsx') if '[' not in str(p)]
urls=['https://xai-compress.vercel.app'+r for r in routes]
urls += ['https://xai-1-be9s.onrender.com/health','https://xai-1-be9s.onrender.com/public/status','https://xai-1-be9s.onrender.com/admin/stats']
urls += ['https://admin-dotnet.onrender.com'+r for r in ['/','/login','/system','/privacy']]
urls += ['https://portal-xai.vercel.app'+r for r in ['/login','/register']]
def probe(url):
    result={'url':url,'checked_at':datetime.now(timezone.utc).isoformat(),'interaction_verified':False}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'XAI-product-audit/1.0'}),timeout=15) as response:
            body=response.read(2000000).decode('utf-8',errors='replace')
            result.update(http_status=response.status,final_url=response.url,result='HTTP_REACHABLE')
            if '/public/status' in url or url.endswith('/health'): result['response']=json.loads(body)
            if 'xai-compress.vercel.app' in url:
                import re
                result['links']=sorted(set(re.findall(r'href="([^"]+)"',body)))
                result['suspect_text']=[t for t in ['42.4%','LIVE','Local Research','Cloud Individual','Enterprise','0.1.0+1'] if t in body]
    except urllib.error.HTTPError as e:result.update(http_status=e.code,result='AUTH_REQUIRED' if e.code in [401,403] else 'HTTP_ERROR')
    except Exception as e:result.update(result='BLOCKED',reason=type(e).__name__)
    return result
with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(probe,urls))
(out/'live-checks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
for result in results: print(result['url'], result['result'], result.get('http_status',''))
