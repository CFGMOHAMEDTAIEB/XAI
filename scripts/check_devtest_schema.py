"""Compare model, actual dev PostgreSQL and additive migration without reading user rows."""
from pathlib import Path
import subprocess
import json

root = Path(__file__).resolve().parents[1]
migration = (root / 'services/api_fastapi/migrations/001_totp_enrollments.sql').read_text()
code = '''
import json, secrets
from sqlalchemy import inspect, text
from app.db import engine
from app.config import settings
from app.models import TotpEnrollment
assert settings.app_env == 'development' and engine.url.database == 'xai_devtest'
expected = {c.name: (str(c.type), c.nullable) for c in TotpEnrollment.__table__.columns}
def verify(connection, schema):
    inspector = inspect(connection)
    actual = {c['name']: (str(c['type']), c['nullable']) for c in inspector.get_columns('totp_enrollments', schema=schema)}
    # PostgreSQL renders SQLAlchemy DateTime as TIMESTAMP.
    normalized = {name: (kind.replace('DATETIME','TIMESTAMP'),nullable) for name,(kind,nullable) in expected.items()}
    assert actual == normalized
    assert inspector.get_pk_constraint('totp_enrollments', schema=schema)['constrained_columns'] == ['user_id']
    assert any(x['column_names'] == ['enrollment_id'] for x in inspector.get_unique_constraints('totp_enrollments', schema=schema))
    assert any(x['constrained_columns'] == ['user_id'] and x['referred_table'] == 'users' for x in inspector.get_foreign_keys('totp_enrollments', schema=schema))
    assert inspector.get_indexes('totp_enrollments', schema=schema)
with engine.connect() as connection:
    verify(connection, 'public')
    schema = 'xai_migration_check_' + secrets.token_hex(8)
    connection.execute(text('CREATE SCHEMA ' + schema))
    connection.execute(text('SET LOCAL search_path TO ' + schema))
    connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
    connection.execute(text(MIGRATION))
    connection.execute(text(MIGRATION))
    verify(connection, schema)
    connection.rollback() # Includes the entire temporary schema and DDL.
print(json.dumps({'database':'PASS','model_columns_nullability':'PASS','primary_foreign_unique_constraints':'PASS','indexes':'PASS','migration_matches_model':'PASS','migration_idempotence':'PASS','temporary_schema_rolled_back':'PASS'}))
'''.replace('MIGRATION', repr(migration))
command = ['docker','compose','--env-file',str(root/'.env.admin-test'),'-f',str(root/'compose.devtest.yml'),'-p','xai-devtest','exec','-T','backend','python','-']
result = subprocess.run(command, input=code, capture_output=True, text=True)
if result.returncode:
    raise SystemExit('Local PostgreSQL schema verification failed; no database rows or connection secrets displayed')
data = json.loads(result.stdout)
out = root/'docs/development-integration'; out.mkdir(parents=True, exist_ok=True)
(out/'database-schema.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
for name, status in data.items(): print(name+' = '+status)
