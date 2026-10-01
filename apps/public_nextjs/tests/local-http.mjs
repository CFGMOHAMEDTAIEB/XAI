import assert from 'node:assert/strict';import {writeFile} from 'node:fs/promises';
const origin=process.env.XAI_PUBLIC_TEST_ORIGIN||'http://127.0.0.1:3100';const routes=['/','/architecture','/contact','/docs','/downloads','/pricing','/privacy','/security','/terms','/robots.txt','/sitemap.xml'];const results=[];
for(const route of routes){
 const response=await fetch(origin+route,{signal:AbortSignal.timeout(20000)});assert.equal(response.status,200,route);const body=await response.text();
 if(route==='/'){assert.ok(body.includes('id="features"'));assert.ok(body.includes('XAICD Desktop')&&body.includes('XAICD Mobile')&&body.includes('XAICD CLI'));assert.ok(!body.includes('/status'))}
 if(route==='/pricing'){assert.ok(body.includes('Commercial subscriptions are not live'));assert.ok(body.includes('Not yet available')&&body.includes('Coming later'))}
 if(route==='/downloads'){
  assert.ok(body.includes('XAICD Downloads')&&body.includes('Choose the client that matches your workflow.'));
  for(const product of ['XAICD Authenticator','XAICD Desktop','XAICD CLI'])assert.ok(body.includes(product));
  assert.ok(!body.includes('XAICD Admin'));
  assert.ok(body.includes('Integrity details')&&body.includes('Available package'));
  assert.ok(!body.includes('Evaluation build')&&!body.includes('Debug-signed')&&!body.includes('For local testing only'));
  assert.ok(!body.includes('TEST_ONLY_DEBUG_SIGNED')&&!body.includes('TEST_ONLY_UNSIGNED')&&!body.includes('LOCAL_PACKAGE_UNSIGNED'));
  assert.ok(!body.includes('Production ready')&&!body.includes('Official signed release'));
  const binaryLinks=[...body.matchAll(/href="([^"]+\.(?:apk|exe|zip|whl))"/g)].map(match=>match[1]);
  assert.equal(binaryLinks.length,3);assert.ok(binaryLinks.every(href=>href.startsWith('/api/releases/')));
 }
 if(route==='/docs'){for(const text of ['Angular','Next.js','Flutter Desktop','XAICD Authenticator','FastAPI','PostgreSQL','ClamAV','YARA','http://10.0.2.2:18002','Selector V2','Brotli-11','Fail-closed processing'])assert.ok(body.includes(text));}
 for(const[,href]of body.matchAll(/href="(\/[^"#?]*)/g)){if(href.startsWith('/_next/')||href.startsWith('/api/releases/')||href.includes('.svg')||href==='/'||href.startsWith('/#'))continue;assert.ok(routes.includes(href)||href==='/download',`Unmapped internal link: ${href} on ${route}`)}
 results.push({route,status:'PASS',scope:'HTTP content and link checks'});
}
const removed=await fetch(origin+'/status');assert.equal(removed.status,404);results.push({route:'/status',status:'PASS',scope:'Removed public route'});
const redirect=await fetch(origin+'/download',{redirect:'manual'});assert.ok([307,308].includes(redirect.status));assert.equal(redirect.headers.get('location'),'/downloads');
const share=await fetch(origin+'/share/audit-invalid-code');assert.equal(share.status,200);assert.ok((await share.text()).includes('Share unavailable'));
await writeFile('../../docs/product-truth-audit/local-http.json',JSON.stringify(results,null,2));console.log(`${results.length} local HTTP product checks passed.`);
