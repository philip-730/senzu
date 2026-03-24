from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, ClassVar

from pydantic import model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from .config import find_config_root, load_config
from .exceptions import SenzuValidationError


def _detect_env() -> str:
    """Return the active env name from ENV, SENZU_ENV, or 'dev'."""
    return os.environ.get("ENV") or os.environ.get("SENZU_ENV") or "dev"


class SenzuSettings(BaseSettings):
    """Pydantic BaseSettings subclass that auto-parses single-quoted JSON strings.

    Sub-class and declare your fields normally.  Fields typed as ``dict``
    (or ``list``) whose env value is a single-quoted JSON string will be
    automatically deserialized.

    Example::

        class Settings(SenzuSettings):
            database_url: str
            google_ads_sa: dict  # stored as '{"type":"service_account",...}'

        settings = Settings()
    """

    # Populated at class-definition time by subclasses (optional override).
    _senzu_env: ClassVar[str | None] = None

    model_config = {
        "extra": "ignore",
        "env_file_encoding": "utf-8",
    }

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # If SENZU_USE_SECRET_MANAGER is set, inject a Secret Manager source.
        # Deferred import: keeps google-cloud-secret-manager out of the import-time
        # critical path — only loaded when the env var is actually set.
        if os.environ.get("SENZU_USE_SECRET_MANAGER", "").lower() in ("1", "true", "yes"):
            from .secret_manager_source import SecretManagerSettingsSource

            return (
                init_settings,
                env_settings,
                SecretManagerSettingsSource(settings_cls),
            )

        # Otherwise resolve the correct .env file.
        env_name = cls._senzu_env or _detect_env()
        env_file = _resolve_env_file(env_name)

        # Deferred import: minor — avoids pulling pydantic_settings internals at module load.
        from pydantic_settings import DotEnvSettingsSource

        return (init_settings, env_settings, DotEnvSettingsSource(settings_cls, env_file=env_file))

    @model_validator(mode="before")
    @classmethod
    def _auto_parse_json_strings(cls, values: Any) -> Any:
        """Deserialize single-quoted JSON strings into Python objects."""
        if not isinstance(values, dict):
            return values
        for key, val in list(values.items()):
            if isinstance(val, str) and val.startswith("'") and val.endswith("'"):
                inner = val[1:-1]
                try:
                    values[key] = json.loads(inner)
                except json.JSONDecodeError:
                    pass  # leave as string
        return values


def _resolve_env_file(env_name: str) -> str | None:
    """Find the .env.<env_name> file by loading senzu.toml."""
    try:
        root = find_config_root()
        cfg = load_config(root)
        env_cfg = cfg.envs.get(env_name)
        if env_cfg:
            return str(root / env_cfg.file)
    except Exception:
        pass
    # Fallback: look for .env.<env_name> in cwd
    candidate = Path(f".env.{env_name}")
    if candidate.exists():
        return str(candidate)
    return None
