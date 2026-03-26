from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretProvider(Protocol):
    def fetch_latest(self, secret_name: str) -> bytes: ...
    def push_version(self, secret_name: str, payload: bytes) -> None: ...
    def ensure_exists(self, secret_name: str) -> None: ...
