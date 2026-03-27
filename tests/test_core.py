from __future__ import annotations

import json

import pytest

from senzu.config import EnvConfig, SecretRef
from senzu.core import (
    diff_env,
    fetch_remote_kv,
    generate_settings_source,
    pull_env,
    push_env,
    read_env_file,
    write_env_file,
)
from senzu.exceptions import KeyCollisionWarning
from senzu.lock import LockEntry


def _env_cfg(*secret_names: str) -> EnvConfig:
    return EnvConfig(
        name="dev",
        project="p",
        file=".env.dev",
        secrets=[SecretRef(secret=s, project="p") for s in secret_names],
    )


# ---------------------------------------------------------------------------
# diff_env
# ---------------------------------------------------------------------------


def test_diff_no_changes():
    assert not diff_env({"A": "1"}, {"A": "1"}).has_drift


def test_diff_added():
    dr = diff_env({"A": "1", "B": "2"}, {"A": "1"})
    assert "B" in dr.added
    assert not dr.removed
    assert not dr.changed


def test_diff_removed():
    assert "B" in diff_env({"A": "1"}, {"A": "1", "B": "2"}).removed


def test_diff_changed():
    dr = diff_env({"A": "new"}, {"A": "old"})
    assert "A" in dr.changed
    assert dr.changed["A"] == ("new", "old")


# ---------------------------------------------------------------------------
# read/write env file
# ---------------------------------------------------------------------------


def test_env_file_roundtrip(tmp_path):
    path = tmp_path / ".env.dev"
    write_env_file(path, {"KEY": "value", "URL": "postgres://localhost"})
    back = read_env_file(path)
    assert back["KEY"] == "value"
    assert back["URL"] == "postgres://localhost"


def test_env_file_single_quoted_json(tmp_path):
    path = tmp_path / ".env.dev"
    write_env_file(path, {"SA": '\'{"type":"service_account"}\''})
    assert "SA=" in path.read_text()
    assert "SA" in read_env_file(path)


def test_read_env_file_missing(tmp_path):
    assert read_env_file(tmp_path / "nonexistent.env") == {}


def test_write_env_file_value_with_space(tmp_path):
    path = tmp_path / ".env.dev"
    write_env_file(path, {"KEY": "hello world"})
    assert 'KEY="hello world"' in path.read_text()
    assert read_env_file(path)["KEY"] == "hello world"


def test_write_env_file_value_with_hash(tmp_path):
    path = tmp_path / ".env.dev"
    write_env_file(path, {"KEY": "val#ue"})
    assert 'KEY="val#ue"' in path.read_text()


def test_write_env_file_value_with_equals(tmp_path):
    path = tmp_path / ".env.dev"
    write_env_file(path, {"KEY": "a=b"})
    assert 'KEY="a=b"' in path.read_text()


def test_write_env_file_double_quoted_value(tmp_path):
    path = tmp_path / ".env.dev"
    write_env_file(path, {"KEY": '"already-quoted"'})
    assert 'KEY="already-quoted"' in path.read_text()
    assert read_env_file(path)["KEY"] == "already-quoted"


# ---------------------------------------------------------------------------
# fetch_remote_kv
# ---------------------------------------------------------------------------


def test_fetch_remote_kv_single_secret(mocker):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"DB": "pg://..."}')
    assert fetch_remote_kv(_env_cfg("app-env")) == {"DB": "pg://..."}


def test_fetch_remote_kv_multiple_secrets_merged(mocker):
    payloads = {"app-env": b'{"DB": "pg://..."}', "api-secrets": b'{"API_KEY": "abc"}'}
    mocker.patch("senzu.core.fetch_secret_latest", side_effect=lambda p, s: payloads[s])
    assert fetch_remote_kv(_env_cfg("app-env", "api-secrets")) == {"DB": "pg://...", "API_KEY": "abc"}


def test_fetch_remote_kv_collision_warns(mocker):
    mocker.patch(
        "senzu.core.fetch_secret_latest",
        side_effect=lambda p, s: f'{{"SHARED": "from-{s}"}}'.encode(),
    )
    with pytest.warns(KeyCollisionWarning, match="SHARED"):
        result = fetch_remote_kv(_env_cfg("secret-a", "secret-b"))
    assert result["SHARED"] == "from-secret-b"


def test_fetch_remote_kv_raw_type_bypasses_detect_format(mocker):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"type": "sa"}')
    detect_mock = mocker.patch("senzu.core.detect_format")
    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[SecretRef(secret="firebase", project="p", type="raw", env_var="FIREBASE_CREDS")],
    )
    result = fetch_remote_kv(env_cfg)
    detect_mock.assert_not_called()
    assert "FIREBASE_CREDS" in result


# ---------------------------------------------------------------------------
# pull_env
# ---------------------------------------------------------------------------


def test_pull_env_happy_path(mocker, tmp_path):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"DB": "pg://...", "KEY": "abc"}')
    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[SecretRef(secret="app-env", project="p")],
    )
    merged, lock_entries = pull_env(env_cfg, tmp_path)
    assert merged == {"DB": "pg://...", "KEY": "abc"}
    assert lock_entries["DB"].secret == "app-env"
    assert lock_entries["DB"].format == "json"


def test_pull_env_raw_type(mocker, tmp_path):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"type":"service_account"}')
    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[SecretRef(secret="firebase", project="p", type="raw", env_var="FIREBASE_CREDS")],
    )
    merged, lock_entries = pull_env(env_cfg, tmp_path)
    assert "FIREBASE_CREDS" in merged
    assert merged["FIREBASE_CREDS"].startswith("'")
    assert lock_entries["FIREBASE_CREDS"].type == "raw"


def test_pull_env_collision_warns(mocker, tmp_path):
    mocker.patch(
        "senzu.core.fetch_secret_latest",
        side_effect=lambda p, s: f'{{"SHARED": "from-{s}"}}'.encode(),
    )
    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[SecretRef(secret="secret-a", project="p"), SecretRef(secret="secret-b", project="p")],
    )
    with pytest.warns(KeyCollisionWarning):
        merged, lock_entries = pull_env(env_cfg, tmp_path)
    assert merged["SHARED"] == "from-secret-b"
    assert lock_entries["SHARED"].secret == "secret-b"


# ---------------------------------------------------------------------------
# push_env
# ---------------------------------------------------------------------------


def test_push_env_no_drift_skips_push(mocker, tmp_path):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"DB": "pg://..."}')
    push_mock = mocker.patch("senzu.core.push_secret_version")
    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[SecretRef(secret="app-env", project="p")],
    )
    results = push_env(env_cfg, {"DB": "pg://..."}, {"DB": LockEntry(secret="app-env", project="p", format="json")}, tmp_path)
    push_mock.assert_not_called()
    assert not results["app-env"].has_drift


def test_push_env_with_drift_pushes(mocker, tmp_path):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"DB": "pg://old"}')
    push_mock = mocker.patch("senzu.core.push_secret_version")
    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[SecretRef(secret="app-env", project="p")],
    )
    results = push_env(env_cfg, {"DB": "pg://new"}, {"DB": LockEntry(secret="app-env", project="p", format="json")}, tmp_path)
    push_mock.assert_called_once()
    assert results["app-env"].has_drift
    assert "DB" in results["app-env"].changed


def test_push_env_key_not_in_lock_warns(mocker, tmp_path):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"DB": "pg://..."}')
    mocker.patch("senzu.core.push_secret_version")
    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[SecretRef(secret="app-env", project="p")],
    )
    with pytest.warns(UserWarning, match="UNTRACKED"):
        push_env(env_cfg, {"DB": "pg://...", "UNTRACKED": "value"}, {"DB": LockEntry(secret="app-env", project="p", format="json")}, tmp_path)


def test_push_env_removes_deleted_keys(mocker, tmp_path):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"DB": "pg://old", "STALE": "remove-me"}')
    push_mock = mocker.patch("senzu.core.push_secret_version")
    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[SecretRef(secret="app-env", project="p")],
    )
    lock_entries = {
        "DB": LockEntry(secret="app-env", project="p", format="json"),
        "STALE": LockEntry(secret="app-env", project="p", format="json"),
    }
    push_env(env_cfg, {"DB": "pg://new"}, lock_entries, tmp_path)
    payload = json.loads(push_mock.call_args[0][2].decode())
    assert "STALE" not in payload
    assert payload["DB"] == "pg://new"


def test_push_env_unrecognized_secret_ref(mocker, tmp_path):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"DB": "pg://old"}')
    mocker.patch("senzu.core.push_secret_version")
    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[SecretRef(secret="app-env", project="p")],
    )
    results = push_env(env_cfg, {"DB": "pg://new"}, {"DB": LockEntry(secret="other-secret", project="p", format="json")}, tmp_path)
    assert results["other-secret"].has_drift


# ---------------------------------------------------------------------------
# generate_settings_source
# ---------------------------------------------------------------------------


def test_generate_settings_source():
    src = generate_settings_source("dev", {"DATABASE_URL": "pg://...", "SA": '\'{"type":"sa"}\''})
    assert "class Settings(SenzuSettings):" in src
    assert "database_url: str" in src
    assert "sa: dict" in src
    assert "Auto-generated" in src


def test_generate_settings_source_empty_kv():
    src = generate_settings_source("dev", {})
    assert "class Settings(SenzuSettings):" in src
    assert "pass" in src
