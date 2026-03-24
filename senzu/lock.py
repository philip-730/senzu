from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .exceptions import LockNotFoundError

LOCK_FILENAME = "senzu.lock"


@dataclass
class LockEntry:
    secret: str
    project: str
    format: Literal["json", "dotenv"] | None = None
    type: Literal["raw"] | None = None


# env_name -> key -> LockEntry
LockData = dict[str, dict[str, LockEntry]]


def load_lock(root: Path) -> LockData:
    lock_path = root / LOCK_FILENAME
    if not lock_path.exists():
        raise LockNotFoundError(
            f"{LOCK_FILENAME} not found. Run `senzu pull` before pushing."
        )
    raw: dict = json.loads(lock_path.read_text())
    result: LockData = {}
    for env_name, keys in raw.items():
        result[env_name] = {}
        for key, entry in keys.items():
            result[env_name][key] = LockEntry(
                secret=entry["secret"],
                project=entry["project"],
                format=entry.get("format"),
                type=entry.get("type"),
            )
    return result


def save_lock(root: Path, data: LockData) -> None:
    lock_path = root / LOCK_FILENAME
    serialized: dict = {}
    for env_name, keys in data.items():
        serialized[env_name] = {}
        for key, entry in keys.items():
            obj: dict = {"secret": entry.secret, "project": entry.project}
            if entry.format is not None:
                obj["format"] = entry.format
            if entry.type is not None:
                obj["type"] = entry.type
            serialized[env_name][key] = obj
    lock_path.write_text(json.dumps(serialized, indent=2) + "\n")
