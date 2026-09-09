// Start local admin in Production with PlatformApi__BaseUrl=http://127.0.0.1:1.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const results=[];
for(const route of ['/','/users','/jobs','/audit','/system','/incidents','/quarantine','/privacy','/login']){
 const response=await fetch('http://127.0.0.1:5100'+route,{signal:AbortSignal.timeout(40000)});
 assert.equal(response.status,200,route);
 const text=await response.text();
 assert.ok(text.includes('Not signed in'),route);
 assert.ok(!text.includes('Demo User')&&!text.includes('JOB-24081'),route);
 if(['/','/users','/jobs','/audit'].includes(route))assert.ok(/sign in|Sign in/.test(text),route);
 if(route==='/system'){assert.ok(text.includes('Service status unavailable'));assert.ok(text.includes('unknown'));assert.ok(!text.includes('Healthy'))}
 if(['/incidents','/quarantine'].includes(route))assert.ok(text.includes('not available from this backend'));
 results.push({route,status:'PASS',scope:'Unauthenticated production environment; failing backend; HTTP prerender only'});
}
await writeFile('docs/product-truth-audit/admin-local-http.json',JSON.stringify(results,null,2));
console.log(`${results.length} admin authorization/error presentation checks passed.`);
