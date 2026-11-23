"""Fixtures: a fresh app and logged-in client on a temporary database."""
import pytest
from ugwatch.app import create_app


@pytest.fixture
def app(tmp_path):
    app=create_app(tmp_path/'test.sqlite3');app.config['TESTING']=True
    return app


@pytest.fixture
def client(app):
    c=app.test_client();c.get('/')
    with c.session_transaction() as s: c.csrf=s['csrf']
    return c
