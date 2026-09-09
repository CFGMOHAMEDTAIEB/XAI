import assert from 'node:assert/strict';
import {test} from 'node:test';
import {productionReleases} from '../lib/releases.mjs';
const candidate={platform:'windows',version:'test-fixture',filename:'fixture.zip',architecture:'x64',releaseNotes:'Test fixture only',sha256:'a'.repeat(64),sizeBytes:12,releasedAt:'2026-01-01',channel:'PRODUCTION',signing:'VERIFIED',installTest:'PASSED',url:'https://github.com/CFGMOHAMEDTAIEB/XAI/releases/download/test-fixture/fixture.zip'};
const read=r=>productionReleases({schemaVersion:1,releases:[r]});
test('no metadata means no downloads',()=>{assert.deepEqual(productionReleases(null),[]);assert.deepEqual(productionReleases({schemaVersion:1,releases:[]}),[])});
test('reject test, unsigned and untested artifacts',()=>{for(const change of [{channel:'TEST'},{signing:'DEBUG'},{signing:'UNSIGNED'},{installTest:'UNVERIFIED'}])assert.deepEqual(read({...candidate,...change}),[])});
test('reject local, fake, mutable and credential URLs',()=>{for(const url of ['C:\\app.zip','http://localhost/app.zip','https://example.com/app.zip','https://github.com/CFGMOHAMEDTAIEB/XAI/releases/latest/download/fixture.zip','https://user:pass@github.com/CFGMOHAMEDTAIEB/XAI/releases/download/v1/fixture.zip'])assert.deepEqual(read({...candidate,url}),[])});
test('require complete reviewed metadata',()=>{assert.equal(read(candidate).length,1);assert.deepEqual(read({...candidate,sha256:'missing'}),[]);assert.deepEqual(read({...candidate,sizeBytes:0}),[])});

