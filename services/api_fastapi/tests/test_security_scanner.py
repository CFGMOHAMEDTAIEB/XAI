"""Unit scanner failures are mocked; live Docker evidence uses the real daemon."""
import hashlib
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app import main, security_scanner as scanner
from app.config import settings
from app.db import Base, get_db

@pytest.fixture
def staged(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'storage_path', str(tmp_path))
    path = tmp_path/'clean.txt'
    path.write_bytes(b'Harmless clean test document')
    return path

def test_clean_result(monkeypatch, staged):
    monkeypatch.setattr(scanner, 'clamav_scan', lambda p: ('clean', []))
    result = scanner.scan_file(staged)
    assert result.clean and result.yara_status == result.clamav_status == 'clean'
    assert result.sha256 == hashlib.sha256(staged.read_bytes()).hexdigest()

def test_real_yara_marker(monkeypatch, staged):
    monkeypatch.setattr(scanner, 'clamav_scan', lambda p: ('clean', []))
    staged.write_bytes(b'XAI_SECURITY_TEST_MARKER')
    result = scanner.scan_file(staged)
    assert not result.clean and result.status == 'blocked'
    assert result.yara_matches == ['XAI_Synthetic_Security_Test']

def test_clamav_unavailable(monkeypatch, staged):
    def unavailable(p): raise OSError('internal-host/path')
    monkeypatch.setattr(scanner, 'clamav_scan', unavailable)
    result = scanner.scan_file(staged)
    assert result.status == 'unavailable' and not result.clean
    assert result.error == 'clamav_unavailable'
    with pytest.raises(HTTPException) as exc:
        scanner.enforce_scan(staged, 'unit')
    assert exc.value.status_code == 503 and 'internal-host' not in exc.value.detail

def test_bad_yara_configuration(monkeypatch, staged):
    monkeypatch.setattr(scanner, 'clamav_scan', lambda p: ('clean', []))
    monkeypatch.setattr(settings, 'yara_rules_path', str(staged))
    result = scanner.scan_file(staged)
    assert result.error == 'yara_unavailable' and not result.clean

def test_outside_storage_is_not_scanned(monkeypatch, staged):
    monkeypatch.setattr(settings, 'storage_path', str(staged.parent/'other'))
    monkeypatch.setattr(scanner, 'clamav_scan', lambda p: pytest.fail('must not scan'))
    assert scanner.scan_file(staged).error == 'invalid_scan_target'

@pytest.mark.parametrize('reply,status,matches', [(b'stream: OK\0','clean',[]),(b'stream: Synthetic.Test FOUND\0','threat',['Synthetic.Test'])])
def test_clamd_protocol(monkeypatch, staged, reply, status, matches):
    sent = []
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def sendall(self, data): sent.append(data)
        def recv(self, n): return reply
    monkeypatch.setattr(scanner, '_connect', lambda t: Socket())
    assert scanner.clamav_scan(staged) == (status, matches)
    assert sent[0] == b'zINSTREAM\0' and sent[-1] == b'\0'*4

@pytest.fixture
def client(monkeypatch, staged):
    # These fixtures contain tiny files. Do not require the production 9 GiB
    # admission reserve from a developer machine; dedicated guard tests below
    # still exercise disk exhaustion, upload bounds, concurrency and timeout.
    monkeypatch.setattr(settings, 'max_upload_bytes', 1048576)
    monkeypatch.setattr(settings, 'max_decompressed_bytes', 1048576)
    monkeypatch.setattr(settings, 'min_free_disk_bytes', 16777216)
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def db():
        with Session(engine) as session: yield session
    main.app.dependency_overrides[get_db] = db
    main.app.dependency_overrides[main.current_user] = lambda: SimpleNamespace(id=123, role='user', email='unit@example.com')
    monkeypatch.setattr(scanner, 'clamav_scan', lambda p: ('clean', []))
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()
        engine.dispose()

def test_clean_upload_order_and_output_scan(monkeypatch, client, staged):
    import xai_compress.compression as engine
    events = []
    scan = scanner.scan_file
    def record(path):
        events.append('scan:'+path.name)
        return scan(path)
    monkeypatch.setattr(scanner, 'scan_file', record)
    def compress(source, artifact, **kw):
        events.append('compress')
        artifact.write_bytes(b'XAIC\x06'+source.read_bytes())
        return {}
    def decompress(artifact, restored, **kw):
        events.append('decompress')
        restored.write_bytes(artifact.read_bytes()[5:])
    monkeypatch.setattr(engine, 'compress_file', compress)
    monkeypatch.setattr(engine, 'decompress_file', decompress)
    response = client.post('/compression/jobs', files={'upload':('clean.txt',b'clean')})
    assert response.status_code == 200, response.text
    assert events == ['scan:source.bin','compress','decompress']
    artifact = client.get('/files/'+str(response.json()['id'])+'/download')
    assert artifact.status_code == 200
    events.clear()
    response = client.post('/compression/decompress', files={'upload':('clean.xaic',artifact.content)})
    assert response.status_code == 200 and response.content == b'clean'
    assert events == ['decompress','scan:restored.bin']

@pytest.mark.parametrize('unavailable,expected', [(False,422),(True,503)])
def test_upload_block_does_not_compress(monkeypatch, client, staged, unavailable, expected):
    import xai_compress.compression as engine
    monkeypatch.setattr(engine, 'compress_file', lambda *a, **kw: pytest.fail('blocked data compressed'))
    if unavailable:
        def fail(p): raise OSError()
        monkeypatch.setattr(scanner, 'clamav_scan', fail)
    body = b'clean' if unavailable else b'XAI_SECURITY_TEST_MARKER'
    response = client.post('/compression/jobs', files={'upload':('test.txt',body)})
    assert response.status_code == expected
    assert list((staged.parent/'123').iterdir()) == []

def test_decompressed_marker_not_released(monkeypatch, client, staged):
    import xai_compress.compression as engine
    events = []
    original_scan = scanner.scan_file
    def scan(path):
        events.append('scan')
        return original_scan(path)
    def decompress(artifact, restored, **kw):
        events.append('decompress')
        restored.write_bytes(b'XAI_SECURITY_TEST_MARKER')
    monkeypatch.setattr(scanner, 'scan_file', scan)
    monkeypatch.setattr(engine, 'decompress_file', decompress)
    response = client.post('/compression/decompress', files={'upload':('test.xaic',b'XAIC\x06fixture')})
    assert response.status_code == 422 and 'XAI_SECURITY_TEST_MARKER' not in response.text
    assert events == ['decompress', 'scan']
    assert list((staged.parent/'123').iterdir()) == []

def test_public_status_sanitized(monkeypatch, client):
    monkeypatch.setattr(main, 'scanner_health', lambda: {'status':'unavailable','clamav':'internal-host','yara':'/secret/rules'})
    response = client.get('/public/status')
    assert response.status_code == 200
    assert response.json()['services']['security_scanner'] == 'unavailable'
    assert response.json()['status'] == 'degraded'
    assert 'internal-host' not in response.text and '/secret' not in response.text
