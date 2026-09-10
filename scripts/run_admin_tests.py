"""Load only local test credentials into the child process; never print them."""
import os
import subprocess
from pathlib import Path
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[1]
config=dotenv_values(root/'.env.admin-test')
if config.get('APP_ENV')!='development':raise SystemExit('Local test configuration required')
env=os.environ.copy()
for key in ['XAI_SEED_ADMIN_EMAIL','XAI_SEED_ADMIN_PASSWORD']:
    if not config.get(key):raise SystemExit('Local test credentials missing')
    env[key]=config[key]
env['XAI_ADMIN_TEST_API']='http://127.0.0.1:18000'
raise SystemExit(subprocess.call(['dotnet','run','--project','tools/admin_integration_tests','--configuration','Release'],cwd=root,env=env))
