import json
import pytest
from pathlib import Path

from senzu.config import EnvConfig, SecretRef
from senzu.core import (
    detect_format,
    diff_env,
    fetch_remote_kv,
    generate_settings_source,
    parse_secret,
    pull_env,
    push_env,
    read_env_file,
    serialize_secret,
    write_env_file,
)
from senzu.exceptions import KeyCollisionWarning, SecretFormatError
from senzu.lock import LockEntry


# ---------------------------------------------------------------------------
# detect_format
# ---------------------------------------------------------------------------


def test_detect_format_json():
    raw = b'{"KEY": "value"}'
    assert detect_format(raw) == "json"


def test_detect_format_dotenv():
    raw = b"KEY=value\nOTHER=123"
    assert detect_format(raw) == "dotenv"


def test_detect_format_hint_wins():
    raw = b'{"KEY": "value"}'
    assert detect_format(raw, hint="dotenv") == "dotenv"


def test_detect_format_error():
    with pytest.raises(SecretFormatError):
        detect_format(b"<xml>not supported</xml>")


# ---------------------------------------------------------------------------
# parse_secret — JSON format
# ---------------------------------------------------------------------------


def _ref(**kwargs) -> SecretRef:
    defaults = {"secret": "s", "project": "p", "format": None, "type": None, "env_var": None}
    defaults.update(kwargs)
    return SecretRef(**defaults)


def test_parse_json_flat_strings():
    raw = b'{"DATABASE_URL": "postgres://...", "API_KEY": "abc"}'
    kv = parse_secret(raw, "json", _ref())
    assert kv == {"DATABASE_URL": "postgres://...", "API_KEY": "abc"}


def test_parse_json_nested_object():
    nested = {"type": "service_account", "project_id": "my-proj"}
    payload = json.dumps({"DATABASE_URL": "pg://...", "SA": nested}).encode()
    kv = parse_secret(payload, "json", _ref())
    assert kv["DATABASE_URL"] == "pg://..."
    assert kv["SA"].startswith("'") and kv["SA"].endswith("'")
    inner = json.loads(kv["SA"][1:-1])
    assert inner["type"] == "service_account"


def test_parse_raw_type():
    blob = {"type": "service_account", "private_key": "..."}
    raw = json.dumps(blob).encode()
    ref = _ref(type="raw", env_var="FIREBASE_CREDS")
    kv = parse_secret(raw, "json", ref)
    assert "FIREBASE_CREDS" in kv
    assert kv["FIREBASE_CREDS"].startswith("'")
    inner = json.loads(kv["FIREBASE_CREDS"][1:-1])
    assert inner["type"] == "service_account"


# ---------------------------------------------------------------------------
# parse_secret — dotenv format
# ---------------------------------------------------------------------------


def test_parse_dotenv_format():
    raw = b"DATABASE_URL=postgres://...\nAPI_KEY=abc123\nDEBUG=false"
    kv = parse_secret(raw, "dotenv", _ref())
    assert kv["DATABASE_URL"] == "postgres://..."
    assert kv["API_KEY"] == "abc123"
    assert kv["DEBUG"] == "false"


# ---------------------------------------------------------------------------
# serialize_secret
# ---------------------------------------------------------------------------


def test_serialize_json_roundtrip():
    original = {"KEY": "value", "NUM": "42"}
    raw = serialize_secret(original, "json")
    back = json.loads(raw.decode())
    assert back == original


def test_serialize_json_nested_roundtrip():
    nested_str = "'" + json.dumps({"type": "sa"}) + "'"
    original = {"DATABASE_URL": "pg://...", "SA": nested_str}
    raw = serialize_secret(original, "json")
    back = json.loads(raw.decode())
    assert back["DATABASE_URL"] == "pg://..."
    assert isinstance(back["SA"], dict)
    assert back["SA"]["type"] == "sa"


def test_serialize_dotenv():
    kv = {"KEY": "value", "URL": "https://example.com"}
    raw = serialize_secret(kv, "dotenv")
    text = raw.decode()
    assert "KEY=value" in text
    assert "URL=https://example.com" in text


# ---------------------------------------------------------------------------
# diff_env
# ---------------------------------------------------------------------------


def test_diff_no_changes():
    dr = diff_env({"A": "1"}, {"A": "1"})
    assert not dr.has_drift


def test_diff_added():
    dr = diff_env({"A": "1", "B": "2"}, {"A": "1"})
    assert "B" in dr.added
    assert not dr.removed
    assert not dr.changed


def test_diff_removed():
    dr = diff_env({"A": "1"}, {"A": "1", "B": "2"})
    assert "B" in dr.removed


def test_diff_changed():
    dr = diff_env({"A": "new"}, {"A": "old"})
    assert "A" in dr.changed
    assert dr.changed["A"] == ("new", "old")


# ---------------------------------------------------------------------------
# read/write env file
# ---------------------------------------------------------------------------


def test_env_file_roundtrip(tmp_path):
    path = tmp_path / ".env.dev"
    kv = {"KEY": "value", "URL": "postgres://localhost"}
    write_env_file(path, kv)
    back = read_env_file(path)
    assert back["KEY"] == "value"
    assert back["URL"] == "postgres://localhost"


def test_env_file_single_quoted_json(tmp_path):
    path = tmp_path / ".env.dev"
    kv = {"SA": '\'{"type":"service_account"}\''}
    write_env_file(path, kv)
    content = path.read_text()
    assert "SA=" in content
    back = read_env_file(path)
    assert "SA" in back


# ---------------------------------------------------------------------------
# generate_settings_source
# ---------------------------------------------------------------------------


def test_generate_settings_source():
    kv = {"DATABASE_URL": "pg://...", "SA": '\'{"type":"sa"}\''}
    src = generate_settings_source("dev", kv)
    assert "class Settings(SenzuSettings):" in src
    assert "database_url: str" in src
    assert "sa: dict" in src
    assert "Auto-generated" in src


# ---------------------------------------------------------------------------
# write_env_file edge cases
# ---------------------------------------------------------------------------


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


def test_read_env_file_missing(tmp_path):
    assert read_env_file(tmp_path / "nonexistent.env") == {}


# ---------------------------------------------------------------------------
# fetch_remote_kv
# ---------------------------------------------------------------------------


def _env_cfg(*secret_names: str) -> EnvConfig:
    return EnvConfig(
        name="dev",
        project="p",
        file=".env.dev",
        secrets=[SecretRef(secret=s, project="p") for s in secret_names],
    )


def test_fetch_remote_kv_single_secret(mocker):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"DB": "pg://..."}')
    result = fetch_remote_kv(_env_cfg("app-env"))
    assert result == {"DB": "pg://..."}


def test_fetch_remote_kv_multiple_secrets_merged(mocker):
    payloads = {
        "app-env": b'{"DB": "pg://..."}',
        "api-secrets": b'{"API_KEY": "abc"}',
    }
    mocker.patch("senzu.core.fetch_secret_latest", side_effect=lambda p, s: payloads[s])
    result = fetch_remote_kv(_env_cfg("app-env", "api-secrets"))
    assert result == {"DB": "pg://...", "API_KEY": "abc"}


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
        name="dev",
        project="p",
        file=".env.dev",
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


def test_pull_env_collision_warns(mocker, tmp_path):
    mocker.patch(
        "senzu.core.fetch_secret_latest",
        side_effect=lambda p, s: f'{{"SHARED": "from-{s}"}}'.encode(),
    )
    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[
            SecretRef(secret="secret-a", project="p"),
            SecretRef(secret="secret-b", project="p"),
        ],
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
    lock_entries = {"DB": LockEntry(secret="app-env", project="p", format="json")}

    results = push_env(env_cfg, {"DB": "pg://..."}, lock_entries, tmp_path)

    push_mock.assert_not_called()
    assert not results["app-env"].has_drift


def test_push_env_with_drift_pushes(mocker, tmp_path):
    mocker.patch("senzu.core.fetch_secret_latest", return_value=b'{"DB": "pg://old"}')
    push_mock = mocker.patch("senzu.core.push_secret_version")

    env_cfg = EnvConfig(
        name="dev", project="p", file=".env.dev",
        secrets=[SecretRef(secret="app-env", project="p")],
    )
    lock_entries = {"DB": LockEntry(secret="app-env", project="p", format="json")}

    results = push_env(env_cfg, {"DB": "pg://new"}, lock_entries, tmp_path)

    push_mock.assert_called_once()
    assert results["app-env"].has_drift
    assert "DB" in results["app-env"].changed
