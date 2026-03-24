import pytest
from pathlib import Path
import toml

from senzu.config import find_config_root, load_config, SecretRef
from senzu.exceptions import ConfigNotFoundError, ConfigParseError


def write_toml(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "senzu.toml"
    p.write_text(toml.dumps(data))
    return tmp_path


def test_simple_config(tmp_path):
    write_toml(
        tmp_path,
        {
            "envs": {
                "dev": {
                    "project": "my-app-dev",
                    "file": ".env.dev",
                    "secrets": [{"secret": "app-env"}],
                }
            }
        },
    )
    cfg = load_config(tmp_path)
    assert "dev" in cfg.envs
    env = cfg.envs["dev"]
    assert env.project == "my-app-dev"
    assert env.file == ".env.dev"
    assert len(env.secrets) == 1
    assert env.secrets[0].secret == "app-env"
    assert env.secrets[0].project == "my-app-dev"  # resolved from env default


def test_secret_project_override(tmp_path):
    write_toml(
        tmp_path,
        {
            "envs": {
                "dev": {
                    "project": "my-app-dev",
                    "file": ".env.dev",
                    "secrets": [
                        {"secret": "app-env"},
                        {"secret": "shared-secret", "project": "shared-infra"},
                    ],
                }
            }
        },
    )
    cfg = load_config(tmp_path)
    secrets = cfg.envs["dev"].secrets
    assert secrets[0].project == "my-app-dev"
    assert secrets[1].project == "shared-infra"


def test_raw_type_requires_env_var(tmp_path):
    write_toml(
        tmp_path,
        {
            "envs": {
                "dev": {
                    "project": "my-app-dev",
                    "file": ".env.dev",
                    "secrets": [{"secret": "firebase-sdk", "type": "raw"}],
                }
            }
        },
    )
    with pytest.raises(ConfigParseError, match="env_var"):
        load_config(tmp_path)


def test_raw_type_with_env_var(tmp_path):
    write_toml(
        tmp_path,
        {
            "envs": {
                "dev": {
                    "project": "my-app-dev",
                    "file": ".env.dev",
                    "secrets": [
                        {"secret": "firebase-sdk", "type": "raw", "env_var": "FIREBASE_CREDS"}
                    ],
                }
            }
        },
    )
    cfg = load_config(tmp_path)
    ref = cfg.envs["dev"].secrets[0]
    assert ref.type == "raw"
    assert ref.env_var == "FIREBASE_CREDS"


def test_missing_config(tmp_path):
    with pytest.raises(ConfigNotFoundError):
        load_config(tmp_path)


def test_invalid_toml(tmp_path):
    (tmp_path / "senzu.toml").write_text("not valid toml [[[")
    with pytest.raises(ConfigParseError):
        load_config(tmp_path)


def test_unknown_format(tmp_path):
    write_toml(
        tmp_path,
        {
            "envs": {
                "dev": {
                    "project": "p",
                    "file": ".env.dev",
                    "secrets": [{"secret": "s", "format": "xml"}],
                }
            }
        },
    )
    with pytest.raises(ConfigParseError, match="format"):
        load_config(tmp_path)


def test_missing_project_raises(tmp_path):
    write_toml(tmp_path, {"envs": {"dev": {"file": ".env.dev", "secrets": []}}})
    with pytest.raises(ConfigParseError, match="project"):
        load_config(tmp_path)


def test_missing_file_raises(tmp_path):
    write_toml(tmp_path, {"envs": {"dev": {"project": "p", "secrets": []}}})
    with pytest.raises(ConfigParseError, match="file"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# find_config_root
# ---------------------------------------------------------------------------


def test_find_config_root_in_cwd(tmp_path, monkeypatch):
    (tmp_path / "senzu.toml").write_text("")
    monkeypatch.chdir(tmp_path)
    assert find_config_root() == tmp_path


def test_find_config_root_from_subdirectory(tmp_path, monkeypatch):
    (tmp_path / "senzu.toml").write_text("")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert find_config_root() == tmp_path


def test_find_config_root_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigNotFoundError):
        find_config_root()
