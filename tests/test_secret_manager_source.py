from __future__ import annotations

import pytest

from senzu.secret_manager_source import SecretManagerSettingsSource
from senzu.settings import SenzuSettings


def _make_source() -> SecretManagerSettingsSource:
    return SecretManagerSettingsSource(SenzuSettings)


def test_get_field_value_returns_none_stub():
    source = _make_source()
    result = source.get_field_value(None, "some_field")
    assert result == (None, "some_field", False)


def test_call_returns_lowercased_keys(mocker, tmp_path):
    mock_cfg = mocker.MagicMock()
    mock_env_cfg = mocker.MagicMock()
    mock_cfg.envs.get.return_value = mock_env_cfg
    mocker.patch("senzu.config.find_config_root", return_value=tmp_path)
    mocker.patch("senzu.config.load_config", return_value=mock_cfg)
    mocker.patch("senzu.core.fetch_remote_kv", return_value={"DATABASE_URL": "pg://...", "API_KEY": "abc"})

    result = _make_source()()

    assert result == {"database_url": "pg://...", "api_key": "abc"}


def test_call_uses_env_env_var(monkeypatch, mocker, tmp_path):
    monkeypatch.setenv("ENV", "prod")
    mock_cfg = mocker.MagicMock()
    mock_cfg.envs.get.return_value = mocker.MagicMock()
    mocker.patch("senzu.config.find_config_root", return_value=tmp_path)
    mocker.patch("senzu.config.load_config", return_value=mock_cfg)
    mocker.patch("senzu.core.fetch_remote_kv", return_value={})

    _make_source()()

    mock_cfg.envs.get.assert_called_once_with("prod")


def test_call_uses_senzu_env(monkeypatch, mocker, tmp_path):
    monkeypatch.setenv("SENZU_ENV", "staging")
    mock_cfg = mocker.MagicMock()
    mock_cfg.envs.get.return_value = mocker.MagicMock()
    mocker.patch("senzu.config.find_config_root", return_value=tmp_path)
    mocker.patch("senzu.config.load_config", return_value=mock_cfg)
    mocker.patch("senzu.core.fetch_remote_kv", return_value={})

    _make_source()()

    mock_cfg.envs.get.assert_called_once_with("staging")


def test_call_defaults_to_dev(monkeypatch, mocker, tmp_path):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("SENZU_ENV", raising=False)
    mock_cfg = mocker.MagicMock()
    mock_cfg.envs.get.return_value = mocker.MagicMock()
    mocker.patch("senzu.config.find_config_root", return_value=tmp_path)
    mocker.patch("senzu.config.load_config", return_value=mock_cfg)
    mocker.patch("senzu.core.fetch_remote_kv", return_value={})

    _make_source()()

    mock_cfg.envs.get.assert_called_once_with("dev")


def test_call_raises_runtime_error_if_config_load_fails(mocker):
    mocker.patch("senzu.config.find_config_root", side_effect=Exception("no config"))

    with pytest.raises(RuntimeError, match="failed to load senzu.toml"):
        _make_source()()


def test_call_raises_runtime_error_if_env_not_found(mocker, tmp_path):
    mock_cfg = mocker.MagicMock()
    mock_cfg.envs.get.return_value = None
    mocker.patch("senzu.config.find_config_root", return_value=tmp_path)
    mocker.patch("senzu.config.load_config", return_value=mock_cfg)

    with pytest.raises(RuntimeError, match="not found in senzu.toml"):
        _make_source()()
