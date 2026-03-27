from __future__ import annotations

import os
from typing import Any

from pydantic_settings import PydanticBaseSettingsSource


class SecretManagerSettingsSource(PydanticBaseSettingsSource):
    """Pydantic settings source that reads secrets from the configured cloud provider.

    Used when SENZU_USE_SECRET_MANAGER=true (Cloud Run / production environments
    where no .env file is present). Supports GCP and AWS based on senzu.toml config.
    """

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        # Deferred imports: keep GCP libs out of the import-time critical path.
        from .config import find_config_root, load_config
        from .core import fetch_remote_kv

        env_name = os.environ.get("ENV") or os.environ.get("SENZU_ENV") or "dev"

        try:
            root = find_config_root()
            cfg = load_config(root)
        except Exception as exc:
            raise RuntimeError(
                f"SENZU_USE_SECRET_MANAGER=true but failed to load senzu.toml: {exc}"
            ) from exc

        env_cfg = cfg.envs.get(env_name)
        if env_cfg is None:
            raise RuntimeError(
                f"SENZU_USE_SECRET_MANAGER=true but env '{env_name}' not found in senzu.toml."
            )

        merged = fetch_remote_kv(env_cfg)
        return {k.lower(): v for k, v in merged.items()}
