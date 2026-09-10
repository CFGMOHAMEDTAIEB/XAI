"""Create ignored local test credentials once; never print credentials."""
from pathlib import Path
import secrets
import subprocess
root=Path(__file__).resolve().parents[1]
path=root/'.env.admin-test'
if subprocess.run(['git','check-ignore','-q',str(path)],cwd=root).returncode:
    raise SystemExit('Refusing to write credentials: local secret file is not ignored')
if path.exists():
    print('Local test configuration already exists; preserved without changes.')
else:
    content={
        'APP_ENV':'development','POSTGRES_PASSWORD':secrets.token_urlsafe(36),
        'JWT_SECRET':secrets.token_urlsafe(48),'XAI_SEED_ADMIN':'true',
        'XAI_SEED_ADMIN_EMAIL':'admin-'+secrets.token_hex(6)+'@example.com',
        'XAI_SEED_ADMIN_PASSWORD':secrets.token_urlsafe(36),
        'SMTP_FROM':'xai-dev@example.com',
    }
    with path.open('x',encoding='utf-8') as target:
        target.write('# Local isolated development only. Never commit or use in production.\n')
        target.write('\n'.join(f'{key}={value}' for key,value in content.items())+'\n')
    print('Local test configuration created in ignored .env.admin-test. No credentials logged.')
