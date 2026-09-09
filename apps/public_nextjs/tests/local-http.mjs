// Run against a locally started production Next.js build on port 3100.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const origin='http://127.0.0.1:3100';
const routes=['/','/architecture','/contact','/docs','/downloads','/pricing','/privacy','/security','/status','/terms','/robots.txt','/sitemap.xml'];
const results=[];
for(const route of routes){
 const response=await fetch(origin+route,{signal:AbortSignal.timeout(20000)});
 assert.equal(response.status,200,route);
 const body=await response.text();
 if(route==='/'){assert.ok(!body.includes('42.4%'));assert.ok(!body.includes('>LIVE<'));assert.ok(body.includes('id="features"'))}
 if(route==='/pricing'){assert.ok(body.includes('Public pricing is not available yet'));assert.ok(!body.includes('Cloud Individual'))}
 if(route==='/downloads'){assert.ok(body.includes('Download unavailable'));assert.ok(!/href="[^\"]+\.(apk|exe|zip)"/.test(body))}
 if(route==='/status'){assert.ok(body.includes('Historical monitoring and uptime percentages are not available'))}
 for(const [,href] of body.matchAll(/href="(\/[^"#?]*)/g)){
   if(href.startsWith('/_next/')||href.includes('.svg')||href==='/'||href.startsWith('/#'))continue;
   assert.ok(routes.includes(href)||href==='/download',`Unmapped internal link: ${href} on ${route}`);
 }
 results.push({route,status:'PASS',scope:'HTTP content and link checks, not browser interaction'});
}
const redirect=await fetch(origin+'/download',{redirect:'manual'});
assert.ok([307,308].includes(redirect.status));assert.equal(redirect.headers.get('location'),'/downloads');
results.push({route:'/download',status:'PASS',scope:'Redirect to /downloads'});
const share=await fetch(origin+'/share/audit-invalid-code',{signal:AbortSignal.timeout(20000)});
assert.equal(share.status,200);assert.ok((await share.text()).includes('Share unavailable'));
results.push({route:'/share/audit-invalid-code',status:'PASS',scope:'Error state for invalid/unverifiable share'});
await writeFile('../../docs/product-truth-audit/local-http.json',JSON.stringify(results,null,2));
console.log(`${results.length} local HTTP product checks passed.`);
