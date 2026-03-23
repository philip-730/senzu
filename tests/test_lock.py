import pytest
from pathlib import Path

from senzu.lock import LockEntry, LockData, load_lock, save_lock, LOCK_FILENAME
from senzu.exceptions import LockNotFoundError


def test_save_and_load(tmp_path):
    data: LockData = {
        "dev": {
            "DATABASE_URL": LockEntry(secret="app-env", project="my-app-dev", format="json"),
            "API_KEY": LockEntry(secret="app-env", project="my-app-dev", format="json"),
        }
    }
    save_lock(tmp_path, data)
    assert (tmp_path / LOCK_FILENAME).exists()

    loaded = load_lock(tmp_path)
    assert "dev" in loaded
    assert "DATABASE_URL" in loaded["dev"]
    entry = loaded["dev"]["DATABASE_URL"]
    assert entry.secret == "app-env"
    assert entry.project == "my-app-dev"
    assert entry.format == "json"


def test_load_missing(tmp_path):
    with pytest.raises(LockNotFoundError):
        load_lock(tmp_path)


def test_save_raw_type(tmp_path):
    data: LockData = {
        "dev": {
            "FIREBASE_CREDS": LockEntry(
                secret="firebase-sdk", project="shared", type="raw"
            )
        }
    }
    save_lock(tmp_path, data)
    loaded = load_lock(tmp_path)
    entry = loaded["dev"]["FIREBASE_CREDS"]
    assert entry.type == "raw"
    assert entry.format is None
