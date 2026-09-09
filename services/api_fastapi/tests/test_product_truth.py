"""Product measurements and privacy, using an isolated database (not live proof)."""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app import main
from app.models import FileRecord, User, ShareCode
from app.security import hash_share_code
from test_mfa_enrollment import flow


def test_admin_measurements_and_unknowns(flow, monkeypatch):
    client, engine, _ = flow
    assert client.get('/admin/stats').status_code == 403
    monkeypatch.setattr(main, 'scanner_health', lambda: {'status':'unavailable'})
    with Session(engine) as db:
        user=db.query(User).one(); user.role='admin'; db.commit()
        empty=main.admin_stats(user,db)
        assert empty['losslessSuccessRate'] is None
        assert empty['openIncidents'] is None and empty['quarantinedFiles'] is None
        for age, verified in [(0,True),(2,False)]:
            db.add(FileRecord(owner_id=user.id,name='private.txt',sha256='0'*64,
                original_size=10,compressed_size=20,codec='test',integrity_verified=verified,
                created_at=datetime.utcnow()-timedelta(days=age)))
        db.commit()
        stats=main.admin_stats(user,db)
        assert stats['jobsToday']==1 and stats['activeUsers']==1
        assert stats['losslessSuccessRate']==50 and stats['bytesSaved']==-20


def test_public_share_does_not_disclose_metadata(flow):
    client, engine, _=flow
    with Session(engine) as db:
        user=db.query(User).one()
        file=FileRecord(owner_id=user.id,name='private-medical-name.txt',sha256='0'*64,
            original_size=10,compressed_size=5,codec='test')
        db.add(file);db.flush()
        db.add(ShareCode(file_id=file.id,sender_id=user.id,recipient_email=user.email,
            code_hash=hash_share_code('audit-valid-code'),expires_at=datetime.utcnow()+timedelta(hours=1)))
        db.commit()
    client.headers.pop('Authorization')
    response=client.get('/public/shares/audit-valid-code')
    assert response.status_code==200
    assert response.json()=={'authentication_required':True}
