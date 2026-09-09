"""Run backend tests with isolated default storage and database."""
import os
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path[:0]=[str(root/'services/api_fastapi'),str(root/'engines/XAI-Compress'),str(root/'scratch/audit-python-deps')]
os.environ['DATABASE_URL']='sqlite://'
os.environ['STORAGE_PATH']=str(root/'scratch/product-truth-storage')
os.environ['APP_ENV']='development'
import pytest
raise SystemExit(pytest.main(['services/api_fastapi/tests','-q','-p','no:cacheprovider','--basetemp=scratch/product-truth-tests']+sys.argv[1:]))
