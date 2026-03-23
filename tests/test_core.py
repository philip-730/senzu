import json
import pytest
from pathlib import Path

from senzu.config import SecretRef
from senzu.core import (
    detect_format,
    parse_secret,
    serialize_secret,
    diff_env,
    generate_settings_source,
    read_env_file,
    write_env_file,
)
from senzu.exceptions import SecretFormatError


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
