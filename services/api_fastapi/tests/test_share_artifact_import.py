"""Focused authenticated import of a locally compressed XAIC artifact."""
from pathlib import Path

from app import main
from app.config import settings
from app.db import get_db
from app.models import FileRecord
from test_security_scanner import client, staged


def test_import_real_xaic_preserves_name_and_creates_share(client, staged, tmp_path):
    from xai_compress.compression import compress_file

    source = tmp_path / 'source.bin'
    source.write_bytes(b'XAICD share import test payload' * 8)
    artifact = tmp_path / 'local.xaic'
    compress_file(source, artifact, mode='static', overwrite=True)
    name = 'xai_compress-0.2.0-python-package-demo-very-long-name.xaic'

    imported = client.post('/files/artifacts', files={'upload': (name, artifact.read_bytes())})
    assert imported.status_code == 201
    assert imported.json()['name'] == name
    file_id = imported.json()['id']
    generator = main.app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        row = db.get(FileRecord, file_id)
        assert row is not None and row.owner_id == 123
        assert row.integrity_verified and row.original_size == source.stat().st_size
        assert Path(row.artifact_path).read_bytes() == artifact.read_bytes()
    finally:
        generator.close()

    downloaded = client.get(f'/files/{file_id}/download')
    assert downloaded.status_code == 200
    assert downloaded.content == artifact.read_bytes()
    assert '.xaic.xaic' not in downloaded.headers['content-disposition']
    assert name in downloaded.headers['content-disposition']

    shared = client.post('/shares', json={'file_id': file_id,
        'recipient_email': 'recipient@example.com', 'expires_minutes': 60})
    assert shared.status_code == 200
    assert shared.json()['share_code']
    assert client.get('/shares').json()[0]['file_name'] == name


def test_import_rejects_wrong_extension_and_invalid_container(client, staged):
    for name, payload in [('not-compressed.txt', b'XAIC\x01broken'),
                          ('fake.xaic', b'not a container'),
                          ('broken.xaic', b'XAIC\x06broken')]:
        response = client.post('/files/artifacts', files={'upload': (name, payload)})
        assert response.status_code == 400
        assert response.json()['detail'] == 'Please select a compressed XAICD file'
    assert list((staged.parent / '123').glob('import-*')) == []


def test_import_requires_full_authentication(client, staged):
    dependency = main.app.dependency_overrides.pop(main.current_user)
    try:
        response = client.post('/files/artifacts', files={'upload': ('file.xaic', b'XAIC\x01test')})
        assert response.status_code == 401
    finally:
        main.app.dependency_overrides[main.current_user] = dependency


def test_preserve_bytes_accepts_xaic_extension_and_keeps_download_identical(client, staged):
    payload = b'PK\x03\x04desktop file content'
    imported = client.post('/files/artifacts?preserve_bytes=true', files={'upload': ('output.xaic', payload)})
    assert imported.status_code == 201
    downloaded = client.get(f"/files/{imported.json()['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == payload
    wrong = client.post('/files/artifacts?preserve_bytes=true', files={'upload': ('output.txt', payload)})
    assert wrong.status_code == 400
