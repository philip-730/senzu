import pytest
from pathlib import Path

from senzu.lock import LockEntry, LockData, load_lock, save_lock, LOCK_FILENAME
from senzu.exceptions import LockNotFoundError


def test_save_and_load(tmp_path):
    data: LockData = {
        "dev": {
            "DATABASE_URL": LockEntry(secret="app-env", project="my-app-dev", provider="gcp", format="json"),
            "API_KEY": LockEntry(secret="app-env", project="my-app-dev", provider="gcp", format="json"),
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
    assert entry.provider == "gcp"
    assert entry.format == "json"


def test_load_missing(tmp_path):
    with pytest.raises(LockNotFoundError):
        load_lock(tmp_path)


def test_save_raw_type(tmp_path):
    data: LockData = {
        "dev": {
            "FIREBASE_CREDS": LockEntry(
                secret="firebase-sdk", project="shared", provider="gcp", type="raw"
            )
        }
    }
    save_lock(tmp_path, data)
    loaded = load_lock(tmp_path)
    entry = loaded["dev"]["FIREBASE_CREDS"]
    assert entry.type == "raw"
    assert entry.format is None


def test_backward_compat_old_lock_file(tmp_path):
    """Old lock files without provider/region fields should default to gcp."""
    import json
    old_lock = {
        "dev": {
            "DB": {"secret": "app-env", "project": "my-proj", "format": "json"}
        }
    }
    (tmp_path / LOCK_FILENAME).write_text(json.dumps(old_lock))
    loaded = load_lock(tmp_path)
    entry = loaded["dev"]["DB"]
    assert entry.provider == "gcp"
    assert entry.region is None
    assert entry.project == "my-proj"


def test_aws_lock_entry_roundtrip(tmp_path):
    data: LockData = {
        "staging": {
            "API_KEY": LockEntry(
                secret="myapp/staging/env",
                project="",
                provider="aws",
                region="us-east-1",
                format="dotenv",
            )
        }
    }
    save_lock(tmp_path, data)
    loaded = load_lock(tmp_path)
    entry = loaded["staging"]["API_KEY"]
    assert entry.provider == "aws"
    assert entry.region == "us-east-1"
    assert entry.project == ""
    assert entry.format == "dotenv"
