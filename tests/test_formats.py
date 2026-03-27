from __future__ import annotations

import json

import pytest

from senzu.config import SecretRef
from senzu.exceptions import SecretFormatError
from senzu.formats import detect_format, parse_secret, serialize_secret


def _ref(**kwargs) -> SecretRef:
    defaults = {"secret": "s", "project": "p", "format": None, "type": None, "env_var": None}
    defaults.update(kwargs)
    return SecretRef(**defaults)


# ---------------------------------------------------------------------------
# detect_format
# ---------------------------------------------------------------------------


def test_detect_format_json():
    assert detect_format(b'{"KEY": "value"}') == "json"


def test_detect_format_dotenv():
    assert detect_format(b"KEY=value\nOTHER=123") == "dotenv"


def test_detect_format_hint_wins():
    assert detect_format(b'{"KEY": "value"}', hint="dotenv") == "dotenv"


def test_detect_format_error():
    with pytest.raises(SecretFormatError):
        detect_format(b"<xml>not supported</xml>")


# ---------------------------------------------------------------------------
# parse_secret — JSON format
# ---------------------------------------------------------------------------


def test_parse_json_flat_strings():
    raw = b'{"DATABASE_URL": "postgres://...", "API_KEY": "abc"}'
    assert parse_secret(raw, "json", _ref()) == {"DATABASE_URL": "postgres://...", "API_KEY": "abc"}


def test_parse_json_nested_object():
    nested = {"type": "service_account", "project_id": "my-proj"}
    raw = json.dumps({"DATABASE_URL": "pg://...", "SA": nested}).encode()
    kv = parse_secret(raw, "json", _ref())
    assert kv["DATABASE_URL"] == "pg://..."
    assert kv["SA"].startswith("'") and kv["SA"].endswith("'")
    assert json.loads(kv["SA"][1:-1])["type"] == "service_account"


def test_parse_raw_type_valid_json():
    blob = {"type": "service_account", "private_key": "..."}
    kv = parse_secret(json.dumps(blob).encode(), "json", _ref(type="raw", env_var="FIREBASE_CREDS"))
    assert kv["FIREBASE_CREDS"].startswith("'")
    assert json.loads(kv["FIREBASE_CREDS"][1:-1])["type"] == "service_account"


def test_parse_raw_type_non_json_stores_raw_text():
    kv = parse_secret(b"plain-text-not-json", "json", _ref(type="raw", env_var="CERT"))
    assert kv["CERT"] == "plain-text-not-json"


# ---------------------------------------------------------------------------
# parse_secret — dotenv format
# ---------------------------------------------------------------------------


def test_parse_dotenv_format():
    raw = b"DATABASE_URL=postgres://...\nAPI_KEY=abc123\nDEBUG=false"
    kv = parse_secret(raw, "dotenv", _ref())
    assert kv == {"DATABASE_URL": "postgres://...", "API_KEY": "abc123", "DEBUG": "false"}


# ---------------------------------------------------------------------------
# serialize_secret
# ---------------------------------------------------------------------------


def test_serialize_json_roundtrip():
    original = {"KEY": "value", "NUM": "42"}
    assert json.loads(serialize_secret(original, "json").decode()) == original


def test_serialize_json_nested_roundtrip():
    nested_str = "'" + json.dumps({"type": "sa"}) + "'"
    raw = serialize_secret({"DATABASE_URL": "pg://...", "SA": nested_str}, "json")
    back = json.loads(raw.decode())
    assert back["DATABASE_URL"] == "pg://..."
    assert isinstance(back["SA"], dict)
    assert back["SA"]["type"] == "sa"


def test_serialize_json_invalid_single_quoted_falls_back_to_string():
    result = json.loads(serialize_secret({"KEY": "'not-valid-json'"}, "json").decode())
    assert result["KEY"] == "'not-valid-json'"


def test_serialize_dotenv():
    text = serialize_secret({"KEY": "value", "URL": "https://example.com"}, "dotenv").decode()
    assert "KEY=value" in text
    assert "URL=https://example.com" in text


def test_serialize_dotenv_quotes_special_chars():
    text = serialize_secret({"MSG": "hello world", "HASH": "val#ue"}, "dotenv").decode()
    assert 'MSG="hello world"' in text
    assert 'HASH="val#ue"' in text
