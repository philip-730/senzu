import json

import pytest
import toml

from senzu.settings import SenzuSettings, _resolve_env_file


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


def test_auto_parse_non_dict_passthrough():
    # model_validator should return non-dict inputs unchanged
    result = SenzuSettings._auto_parse_json_strings("just-a-string")
    assert result == "just-a-string"


# ---------------------------------------------------------------------------
# settings_customise_sources — SENZU_USE_SECRET_MANAGER branch
# ---------------------------------------------------------------------------


def test_settings_customise_sources_uses_secret_manager(monkeypatch, mocker):
    monkeypatch.setenv("SENZU_USE_SECRET_MANAGER", "true")
    mock_cls = mocker.patch("senzu.secret_manager_source.SecretManagerSettingsSource")
    mock_instance = mocker.MagicMock()
    mock_cls.return_value = mock_instance

    dummy = mocker.MagicMock()
    sources = SenzuSettings.settings_customise_sources(
        SenzuSettings,
        init_settings=dummy,
        env_settings=dummy,
        dotenv_settings=dummy,
        file_secret_settings=dummy,
    )

    mock_cls.assert_called_once_with(SenzuSettings)
    assert mock_instance in sources


# ---------------------------------------------------------------------------
# _resolve_env_file
# ---------------------------------------------------------------------------


def test_resolve_env_file_reads_from_config(tmp_path, monkeypatch):
    (tmp_path / "senzu.toml").write_text(
        toml.dumps({"envs": {"dev": {"project": "p", "file": ".env.dev", "secrets": []}}})
    )
    monkeypatch.chdir(tmp_path)
    result = _resolve_env_file("dev")
    assert result == str(tmp_path / ".env.dev")


def test_resolve_env_file_returns_none_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no senzu.toml, no .env.staging
    result = _resolve_env_file("staging")
    assert result is None
