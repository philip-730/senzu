from __future__ import annotations

import os
from typing import Any

from pydantic_settings import PydanticBaseSettingsSource


class SecretManagerSettingsSource(PydanticBaseSettingsSource):
    """Pydantic settings source that reads directly from GCP Secret Manager.

    Used when SENZU_USE_SECRET_MANAGER=true (Cloud Run / production environments
    where no .env file is present).
    """

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        from .config import find_config_root, load_config
        from .core import detect_format, fetch_secret_latest, parse_secret

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

        merged: dict[str, Any] = {}
        for secret_ref in env_cfg.secrets:
            raw = fetch_secret_latest(secret_ref.project, secret_ref.secret)
            fmt = "json" if secret_ref.type == "raw" else detect_format(raw, secret_ref.format)
            kv = parse_secret(raw, fmt, secret_ref)
            merged.update(kv)

        return merged
