from __future__ import annotations

from ..exceptions import ConfigParseError
from .base import SecretProvider


def get_provider_for_ref(ref) -> SecretProvider:
    """Return a SecretProvider for a SecretRef."""
    provider = getattr(ref, "provider", None) or "gcp"
    if provider == "gcp":
        from .gcp import GcpProvider
        return GcpProvider(ref.project)
    elif provider == "aws":
        from .aws import AwsProvider
        return AwsProvider(ref.region)
    raise ConfigParseError(f"Unknown provider '{provider}'.")


def get_provider_for_lock_entry(entry) -> SecretProvider:
    """Return a SecretProvider for a LockEntry."""
    provider = getattr(entry, "provider", None) or "gcp"
    if provider == "gcp":
        from .gcp import GcpProvider
        return GcpProvider(entry.project)
    elif provider == "aws":
        from .aws import AwsProvider
        return AwsProvider(entry.region)
    raise ConfigParseError(f"Unknown provider '{provider}'.")
