"""Senzu — Secret env sync for GCP teams."""

from .settings import SenzuSettings
from .exceptions import (
    SenzuError,
    ConfigNotFoundError,
    ConfigParseError,
    LockNotFoundError,
    SecretFetchError,
    SecretFormatError,
    SecretPushError,
    RemoteDriftError,
    SenzuValidationError,
)

__all__ = [
    "SenzuSettings",
    "SenzuError",
    "ConfigNotFoundError",
    "ConfigParseError",
    "LockNotFoundError",
    "SecretFetchError",
    "SecretFormatError",
    "SecretPushError",
    "RemoteDriftError",
    "SenzuValidationError",
]

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("senzu")
except PackageNotFoundError:
    __version__ = "unknown"
