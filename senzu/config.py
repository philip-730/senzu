from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import toml

from .exceptions import ConfigNotFoundError, ConfigParseError

CONFIG_FILENAME = "senzu.toml"


@dataclass
class SecretRef:
    secret: str
    project: str  # resolved — always has a value after loading
    format: Literal["json", "dotenv"] | None = None  # None = auto-detect
    type: Literal["raw"] | None = None  # None = env-style (key/value map)
    env_var: str | None = None  # only used when type="raw"


@dataclass
class EnvConfig:
    name: str
    project: str
    file: str
    secrets: list[SecretRef] = field(default_factory=list)


@dataclass
class SenzuConfig:
    envs: dict[str, EnvConfig] = field(default_factory=dict)
    config_path: Path = field(default_factory=Path)


def load_config(root: Path | None = None) -> SenzuConfig:
    """Load and validate senzu.toml from *root* (default: cwd)."""
    if root is None:
        root = Path.cwd()

    config_path = root / CONFIG_FILENAME
    if not config_path.exists():
        raise ConfigNotFoundError(
            f"No {CONFIG_FILENAME} found. Run `senzu init` to get started."
        )

    try:
        data = toml.loads(config_path.read_text())
    except toml.TomlDecodeError as exc:
        raise ConfigParseError(f"Failed to parse {CONFIG_FILENAME}: {exc}") from exc

    envs: dict[str, EnvConfig] = {}
    envs_data = data.get("envs", {})
    if not isinstance(envs_data, dict):
        raise ConfigParseError(f"{CONFIG_FILENAME}: 'envs' must be a table.")

    for env_name, env_data in envs_data.items():
        if not isinstance(env_data, dict):
            raise ConfigParseError(
                f"{CONFIG_FILENAME}: 'envs.{env_name}' must be a table."
            )

        default_project = env_data.get("project")
        if not default_project:
            raise ConfigParseError(
                f"{CONFIG_FILENAME}: 'envs.{env_name}.project' is required."
            )

        env_file = env_data.get("file")
        if not env_file:
            raise ConfigParseError(
                f"{CONFIG_FILENAME}: 'envs.{env_name}.file' is required."
            )

        secrets_raw = env_data.get("secrets", [])
        if not isinstance(secrets_raw, list):
            raise ConfigParseError(
                f"{CONFIG_FILENAME}: 'envs.{env_name}.secrets' must be an array."
            )

        secrets: list[SecretRef] = []
        for s in secrets_raw:
            if not isinstance(s, dict) or "secret" not in s:
                raise ConfigParseError(
                    f"{CONFIG_FILENAME}: each secret in 'envs.{env_name}.secrets' "
                    "must have a 'secret' key."
                )

            secret_type = s.get("type")
            if secret_type not in (None, "raw"):
                raise ConfigParseError(
                    f"{CONFIG_FILENAME}: unknown type '{secret_type}' in "
                    f"'envs.{env_name}.secrets'."
                )

            secret_format = s.get("format")
            if secret_format not in (None, "json", "dotenv"):
                raise ConfigParseError(
                    f"{CONFIG_FILENAME}: unknown format '{secret_format}' in "
                    f"'envs.{env_name}.secrets'."
                )

            env_var = s.get("env_var")
            if secret_type == "raw" and not env_var:
                raise ConfigParseError(
                    f"{CONFIG_FILENAME}: 'env_var' is required for type='raw' "
                    f"secrets in 'envs.{env_name}'."
                )

            secrets.append(
                SecretRef(
                    secret=s["secret"],
                    project=s.get("project", default_project),
                    format=secret_format,
                    type=secret_type,
                    env_var=env_var,
                )
            )

        envs[env_name] = EnvConfig(
            name=env_name,
            project=default_project,
            file=env_file,
            secrets=secrets,
        )

    return SenzuConfig(envs=envs, config_path=config_path)


def find_config_root() -> Path:
    """Walk up from cwd to find the directory containing senzu.toml."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / CONFIG_FILENAME).exists():
            return parent
    raise ConfigNotFoundError(
        f"No {CONFIG_FILENAME} found. Run `senzu init` to get started."
    )
