import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app import main, security_scanner as scanner, resource_guard as guard
from app.config import settings, Settings
from app.db import get_db
from app.models import AuditEvent, FileRecord
from test_security_scanner import client, staged

@pytest.mark.parametrize('content', ['', 'rule broken {', 'rule same { condition: true }\nrule same { condition: true }'])
def test_invalid_rules_fail_closed(monkeypatch, staged, content):
    rules = staged.parent/'rules'; rules.mkdir()
    if content: (rules/'rules.yar').write_text(content)
    monkeypatch.setattr(settings, 'yara_rules_path', str(rules))
    monkeypatch.setattr(scanner, 'clamav_scan', lambda p: ('clean', []))
    assert scanner.scan_file(staged).status == 'unavailable'

def test_duplicate_names_across_files_fail(staged):
    rules = staged.parent/'duplicates'; rules.mkdir()
    for name in ('one','two'): (rules/(name+'.yar')).write_text('rule same { condition: true }')
    with pytest.raises(ValueError, match='duplicate'): scanner.load_yara_rules(str(rules))

def test_production_rejects_synthetic_rule(monkeypatch, staged):
    monkeypatch.setattr(settings, 'app_env', 'production')
    monkeypatch.setattr(scanner, 'clamav_scan', lambda p: ('clean', []))
    assert scanner.scan_file(staged).yara_status == 'unavailable'

@pytest.mark.parametrize('overrides', [{'security_scan_required':False}, {'cors_origins':'https://*.example.com'}, {'yara_rules_path':'/app/security/yara/test'}, {'max_heavy_requests':0}])
def test_production_rejects_unsafe_config(overrides):
    config = dict(app_env='production', jwt_secret='a'*48, database_url='postgresql+psycopg://u:p@db/xai', cors_origins='https://xai-usg.vercel.app')
    config.update(overrides)
    with pytest.raises(ValueError): Settings(_env_file=None, **config)

def test_production_defaults_empty_rules_directory():
    config = Settings(_env_file=None, app_env='production', jwt_secret='a'*48, database_url='postgresql+psycopg://u:p@db/xai', cors_origins='https://xai-usg.vercel.app', yara_rules_path='')
    assert config.security_scan_required and Path(config.yara_rules_path).name == 'production'
    with pytest.raises(ValueError, match='No YARA'): scanner.load_yara_rules(config.yara_rules_path)

@pytest.mark.parametrize('payload', [b'', b'fake', b'XAIC\x04bad', b'XAIC\x06broken'])
def test_malformed_container_cleanup(client, staged, payload):
    response = client.post('/compression/decompress', files={'upload':('../../escape.xaic',payload)})
    assert response.status_code == 400
    assert list((staged.parent/'123').iterdir()) == []

def test_output_limit_forwarded_and_error_sanitized(monkeypatch, client, staged):
    import xai_compress.compression as engine
    def decompress(a,b,**kw):
        assert kw['max_output_size'] == settings.max_decompressed_bytes
        b.write_bytes(b'partial')
        raise ValueError('/sensitive/path: expansion limit')
    monkeypatch.setattr(engine,'decompress_file',decompress)
    response=client.post('/compression/decompress',files={'upload':('input.xaic',b'XAIC\x06test')})
    assert response.status_code == 400 and '/sensitive' not in response.text
    assert list((staged.parent/'123').iterdir()) == []

def test_compression_error_sanitized_and_cleanup(monkeypatch, client, staged):
    import xai_compress.compression as engine
    def fail(*a,**kw): raise RuntimeError('clamav:3310 /private/rules traceback')
    monkeypatch.setattr(engine,'compress_file',fail)
    response=client.post('/compression/jobs',files={'upload':('file.txt',b'clean')})
    assert response.status_code==500 and response.json()=={'detail':'Compression failed'}
    assert list((staged.parent/'123').iterdir())==[]

@pytest.mark.parametrize('threat,status', [(True,422),(False,503)])
def test_scan_errors_sanitized(monkeypatch, client, threat, status):
    monkeypatch.setattr(scanner,'clamav_scan',lambda p: ('threat',['private-host:3310/rules']) if threat else (_ for _ in ()).throw(OSError('secret path')))
    response=client.post('/compression/jobs',files={'upload':('file.txt',b'clean')})
    assert response.status_code==status
    assert response.json()['detail'] in ('File rejected by security policy','File security verification unavailable; retry later')

def test_cleanup_failure_logged_without_path(monkeypatch, staged, caplog):
    def fail(path): raise PermissionError(str(path))
    monkeypatch.setattr(guard.shutil,'rmtree',fail)
    guard.cleanup_work(staged.parent/'private')
    assert 'temporary_cleanup_failed' in caplog.text and str(staged.parent) not in caplog.text

def test_security_audit_and_logs(monkeypatch, client, staged, caplog):
    caplog.set_level('INFO',logger='uvicorn.error.security')
    generator=main.app.dependency_overrides[get_db](); db=next(generator)
    try:
        scanner.enforce_scan(staged,'unit',request_id='request-123',user_id=123,db=db)
        event=db.scalar(select(AuditEvent).where(AuditEvent.action=='security.scan'))
        data=json.loads(event.details)
        assert event.resource=='request-123' and event.result=='allowed' and data['allowed']
        assert len(data['sha256'])==64 and data['duration_seconds']>=0 and data['timestamp']
        log=json.loads(next(r.message.split('security_scan ',1)[1] for r in caplog.records if 'security_scan ' in r.message))
        assert log['user_id']==123 and log['request_id']=='request-123'
        assert str(staged) not in caplog.text and staged.read_text() not in caplog.text
    finally: generator.close()

def test_owner_history_and_admin_authorization(client, staged):
    generator=main.app.dependency_overrides[get_db](); db=next(generator)
    try:
        for owner in (123,999):
            db.add(FileRecord(owner_id=owner,name='file.txt',sha256='a'*64,original_size=1,compressed_size=1,codec='test',artifact_path=str(staged)))
        db.commit()
        rows=db.scalars(select(FileRecord).order_by(FileRecord.id)).all()
        assert client.get('/files/'+str(rows[0].id)+'/download').status_code==200
        assert client.get('/files/'+str(rows[1].id)+'/download').status_code==404
        history=client.get('/history')
        assert history.status_code==200 and len(history.json())==1
        assert client.get('/admin/stats').status_code==403
        assert client.get('/admin/audit').status_code==403
        assert client.post('/compression/decompress?file_id='+str(rows[1].id)).status_code==422
        main.app.dependency_overrides.pop(main.current_user)
        assert client.get('/files/'+str(rows[0].id)+'/download').status_code==401
    finally: generator.close()

def test_cors_rejects_unlisted_origin(client):
    response=client.options('/compression/jobs',headers={'Origin':'https://untrusted.example','Access-Control-Request-Method':'POST'})
    assert response.status_code==400 and 'access-control-allow-origin' not in response.headers

@pytest.mark.parametrize('scenario,expected',[('length',413),('stream',413),('busy',503),('disk',503),('timeout',408)])
def test_preparse_resource_bounds(monkeypatch, staged, scenario, expected):
    monkeypatch.setattr(settings,'max_upload_bytes',1)
    monkeypatch.setattr(settings,'upload_idle_timeout',0.01)
    monkeypatch.setattr(guard.shutil,'disk_usage',lambda p: SimpleNamespace(free=0 if scenario=='disk' else 10**12))
    async def downstream(scope,receive,send):
        await receive()
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':b'ok'})
    middleware=guard.ResourceGuard(downstream)
    if scenario=='busy': middleware.active=settings.max_heavy_requests
    messages=[]
    async def receive():
        if scenario=='timeout': await asyncio.sleep(1)
        return {'type':'http.request','body':b'x'*(1048578 if scenario=='stream' else 0),'more_body':False}
    async def send(message): messages.append(message)
    scope={'type':'http','path':'/compression/jobs','headers':[(b'content-length',b'1048578')] if scenario=='length' else []}
    asyncio.run(middleware(scope,receive,send))
    assert messages[0]['status']==expected
    if scenario!='busy': assert middleware.active==0
