import json

import pytest

from senzu.settings import SenzuSettings


class _DictField(SenzuSettings):
    sa: dict


class _StrField(SenzuSettings):
    name: str


def test_auto_parse_deserializes_single_quoted_json_dict():
    blob = {"type": "service_account", "project_id": "my-proj"}
    s = _DictField(sa=f"'{json.dumps(blob)}'")
    assert s.sa == blob


def test_auto_parse_leaves_regular_string():
    s = _StrField(name="hello")
    assert s.name == "hello"


def test_auto_parse_invalid_json_stays_string():
    # Single-quoted but not valid JSON — field is typed str so it stays as-is
    class _S(SenzuSettings):
        raw: str

    s = _S(raw="'not-valid-json'")
    assert s.raw == "'not-valid-json'"
