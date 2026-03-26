from __future__ import annotations

from ..exceptions import ConfigParseError
from .base import SecretProvider

_cache: dict[tuple, SecretProvider] = {}


def _get_gcp(project: str) -> SecretProvider:
    key = ("gcp", project)
    if key not in _cache:
        from .gcp import GcpProvider

        _cache[key] = GcpProvider(project)
    return _cache[key]


def _get_aws(region: str) -> SecretProvider:
    key = ("aws", region)
    if key not in _cache:
        from .aws import AwsProvider

        _cache[key] = AwsProvider(region)
    return _cache[key]


def get_provider_for_ref(ref) -> SecretProvider:
    """Return a SecretProvider for a SecretRef."""
    provider = getattr(ref, "provider", None) or "gcp"
    if provider == "gcp":
        return _get_gcp(ref.project)
    elif provider == "aws":
        return _get_aws(ref.region)
    raise ConfigParseError(f"Unknown provider '{provider}'.")


def get_provider_for_lock_entry(entry) -> SecretProvider:
    """Return a SecretProvider for a LockEntry."""
    provider = getattr(entry, "provider", None) or "gcp"
    if provider == "gcp":
        return _get_gcp(entry.project)
    elif provider == "aws":
        return _get_aws(entry.region)
    raise ConfigParseError(f"Unknown provider '{provider}'.")
