import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from scryfallmcp.moxfield.auth import CredentialManager, Credentials


@pytest.fixture
def creds_file(tmp_path):
    return tmp_path / "credentials.json"


def test_credentials_are_expired_when_past_expiry():
    creds = Credentials(
        token="Bearer abc",
        cookies={"session": "x"},
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    assert creds.is_expired()


def test_credentials_are_valid_when_future_expiry():
    creds = Credentials(
        token="Bearer abc",
        cookies={"session": "x"},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert not creds.is_expired()


def test_load_returns_none_when_file_missing(creds_file):
    manager = CredentialManager(creds_path=creds_file)
    assert manager.load() is None


def test_save_and_load_roundtrip(creds_file):
    manager = CredentialManager(creds_path=creds_file)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    creds = Credentials(token="Bearer xyz", cookies={"_moxfield_session": "abc"}, expires_at=expires)
    manager.save(creds)
    loaded = manager.load()
    assert loaded.token == "Bearer xyz"
    assert loaded.cookies == {"_moxfield_session": "abc"}
    assert not loaded.is_expired()


def test_save_sets_file_permissions(creds_file):
    manager = CredentialManager(creds_path=creds_file)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    creds = Credentials(token="t", cookies={}, expires_at=expires)
    manager.save(creds)
    mode = oct(os.stat(creds_file).st_mode)[-3:]
    assert mode == "600"
