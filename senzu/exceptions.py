class SenzuError(Exception):
    """Base exception for all Senzu errors."""


class ConfigNotFoundError(SenzuError):
    """senzu.toml not found in the current directory."""


class ConfigParseError(SenzuError):
    """senzu.toml could not be parsed."""


class LockNotFoundError(SenzuError):
    """senzu.lock not found — user needs to pull first."""


class ProviderNotInstalledError(SenzuError):
    """Required cloud provider SDK is not installed."""


class SecretFetchError(SenzuError):
    """Failed to fetch a secret from Secret Manager."""


class SecretFormatError(SenzuError):
    """Secret value could not be parsed as JSON or dotenv."""


class SecretPushError(SenzuError):
    """Failed to push a new secret version."""


class RemoteDriftError(SenzuError):
    """Remote has changes not present in the local file."""


class KeyCollisionWarning(UserWarning):
    """A key appears in more than one secret for an env."""


class SenzuValidationError(SenzuError):
    """Settings schema validation failed — required keys missing."""
