from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import FileRecord, ShareCode, User
from test_mfa_enrollment import flow, register_and_login


def add_artifact(engine, tmp_path, owner_email='person@example.com'):
    artifact=tmp_path/'owned.xaic';artifact.write_bytes(b'XAIC\x01test-artifact')
    with Session(engine) as db:
        owner=db.query(User).filter_by(email=owner_email).one()
        row=FileRecord(owner_id=owner.id,name='owned.bin',sha256='0'*64,original_size=20,
            compressed_size=16,codec='test',artifact_path=str(artifact),integrity_verified=True,status='completed')
        db.add(row);db.commit();return row.id


def test_share_list_redeem_download_revoke_and_ownership(flow, tmp_path):
    client,engine,sent=flow;owner_token=client.headers['Authorization']
    file_id=add_artifact(engine,tmp_path)
    recipient_token=register_and_login(client,sent,'recipient@example.com','+33612345679')

    client.headers['Authorization']=owner_token
    created=client.post('/shares',json={'file_id':file_id,'recipient_email':'recipient@example.com','expires_minutes':60,'max_downloads':2})
    assert created.status_code==200;code=created.json()['share_code']
    listed=client.get('/shares');assert listed.status_code==200
    item=listed.json()[0];assert item['file_name']=='owned.bin' and item['status']=='active'
    assert 'share_code' not in item and 'code_hash' not in item

    client.headers['Authorization']='Bearer '+recipient_token
    assert client.get(f'/files/{file_id}/download').status_code==404
    assert client.post('/shares/redeem',json={'code':code}).status_code==200
    assert client.post('/shares/download',json={'code':code}).status_code==200
    assert client.post(f"/shares/{item['id']}/revoke").status_code==404

    client.headers['Authorization']=owner_token
    assert client.post(f"/shares/{item['id']}/revoke").json()=={'status':'revoked'}
    assert client.get('/shares').json()[0]['status']=='revoked'
    client.headers['Authorization']='Bearer '+recipient_token
    assert client.post('/shares/redeem',json={'code':code}).status_code==404
    assert client.post('/shares/download',json={'code':code}).status_code==404


def test_expired_and_exhausted_shares_are_denied(flow, tmp_path):
    client,engine,sent=flow;owner_token=client.headers['Authorization'];file_id=add_artifact(engine,tmp_path)
    recipient_token=register_and_login(client,sent,'recipient@example.com','+33612345679')
    client.headers['Authorization']=owner_token
    code=client.post('/shares',json={'file_id':file_id,'recipient_email':'recipient@example.com','expires_minutes':60,'max_downloads':1}).json()['share_code']
    with Session(engine) as db:
        row=db.query(ShareCode).one();row.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert client.get('/shares').json()[0]['status']=='expired'
    client.headers['Authorization']='Bearer '+recipient_token
    assert client.post('/shares/redeem',json={'code':code}).status_code==404
    assert client.post('/shares/download',json={'code':code}).status_code==404
