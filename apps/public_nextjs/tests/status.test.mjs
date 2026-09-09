import assert from 'node:assert/strict';
import {test} from 'node:test';
import {normalizeStatus,serviceLabels} from '../lib/status.mjs';
const all=Object.fromEntries(Object.keys(serviceLabels).map(key=>[key,'operational']));
test('missing or malformed data is unknown',()=>{assert.equal(normalizeStatus(null).overall,'unknown');assert.equal(normalizeStatus({services:{api:'healthy'}}).services.api,'unknown')});
test('unknown never becomes operational',()=>assert.equal(normalizeStatus({status:'operational',services:{...all,notifications:'unknown'}}).overall,'unknown'));
test('scanner degradation is visible despite upstream overall',()=>{const result=normalizeStatus({status:'operational',services:{...all,security_scanner:'unavailable'}});assert.equal(result.overall,'degraded');assert.equal(result.services.security_scanner,'unavailable')});
test('only all operational is operational',()=>assert.equal(normalizeStatus({services:all}).overall,'operational'));
