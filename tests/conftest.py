"""Disposable schema on Supabase only; never reset the application's public schema."""
import os, uuid, tempfile
from pathlib import Path
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

load_dotenv(Path(os.getenv('LOCALAPPDATA',''))/'Ternfold'/'.env', encoding='utf-8-sig')
load_dotenv(Path(__file__).resolve().parents[1]/'.env', encoding='utf-8-sig')
_schema = 'ternfold_test_' + uuid.uuid4().hex
_admin = None

def pytest_configure(config):
    global _admin
    if os.getenv('TERNFOLD_RUN_DB_TESTS') != '1':
        return
    url=make_url(os.environ['SUPABASE_DATABASE_URL']).set(drivername='postgresql+psycopg')
    if not url.host or not url.host.endswith(('.supabase.co','.pooler.supabase.com')):
        raise RuntimeError('Tests require a Supabase connection.')
    url=url.update_query_dict({'sslmode':'require','connect_timeout':'10'})
    _admin=create_engine(url)
    with _admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {_schema}'))
    os.environ['SUPABASE_DATABASE_URL']=url.update_query_dict({'options':f'-csearch_path={_schema}'}).render_as_string(hide_password=False)
    os.environ['TERNFOLD_STORAGE_ROOT']=tempfile.mkdtemp(prefix='ternfold-test-evidence-')
    os.environ['TERNFOLD_STORAGE_BACKEND']='local'
    os.environ['TERNFOLD_SECURE_COOKIES']='0'
    os.environ['TERNFOLD_AI_PROVIDER']='manual'

def pytest_ignore_collect(collection_path, config):
    return collection_path.name in {'test_workflow.py','test_regressions.py'} and os.getenv('TERNFOLD_RUN_DB_TESTS') != '1'

def pytest_unconfigure(config):
    if _admin is not None:
        with _admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {_schema} CASCADE'))
        _admin.dispose()
