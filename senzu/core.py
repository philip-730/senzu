from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from .config import EnvConfig, SecretRef
from .exceptions import KeyCollisionWarning
from .formats import SecretFormat, detect_format, parse_secret, serialize_secret
from .gcp import fetch_secret_latest, push_secret_version
from .lock import LockData, LockEntry


# ---------------------------------------------------------------------------
# .env file read/write
# ---------------------------------------------------------------------------


def read_env_file(path: Path) -> dict[str, str]:
    """Read a .env file into a flat {KEY: value} dict."""
    if not path.exists():
        return {}
    return {k: v or "" for k, v in dotenv_values(path).items()}


def write_env_file(path: Path, kv: dict[str, str]) -> None:
    """Write a flat {KEY: value} dict to a .env file."""
    lines = []
    for key, val in kv.items():
        # Values that are already single-quoted (nested/raw JSON) go as-is
        if val.startswith("'") and val.endswith("'"):
            lines.append(f"{key}={val}")
        elif val.startswith('"') and val.endswith('"'):
            lines.append(f"{key}={val}")
        elif any(c in val for c in (" ", "#", "\n", "=")):
            escaped = val.replace('"', '\\"')
            lines.append(f'{key}="{escaped}"')
        else:
            lines.append(f"{key}={val}")
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Fetch remote secrets
# ---------------------------------------------------------------------------


def fetch_remote_kv(env_cfg: EnvConfig) -> dict[str, str]:
    """Fetch and merge all secrets for *env_cfg* into a flat {KEY: value} dict."""
    merged: dict[str, str] = {}
    seen: dict[str, str] = {}  # key -> secret name, for collision detection
    for secret_ref in env_cfg.secrets:
        raw = fetch_secret_latest(secret_ref.project, secret_ref.secret)
        fmt = "json" if secret_ref.type == "raw" else detect_format(raw, secret_ref.format)
        kv = parse_secret(raw, fmt, secret_ref)
        for key, val in kv.items():
            if key in merged:
                warnings.warn(
                    f"Key collision — '{key}' found in both "
                    f"'{seen[key]}' and '{secret_ref.secret}'. "
                    f"Using value from '{secret_ref.secret}' (last wins). "
                    "Check your secret organisation.",
                    KeyCollisionWarning,
                    stacklevel=2,
                )
            merged[key] = val
            seen[key] = secret_ref.secret
    return merged


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


@dataclass
class DiffResult:
    added: dict[str, str]      # keys only in local
    removed: dict[str, str]    # keys only in remote
    changed: dict[str, tuple[str, str]]  # keys in both but value differs: {key: (local, remote)}

    @property
    def has_drift(self) -> bool:
        return bool(self.added or self.removed or self.changed)


def diff_env(local_kv: dict[str, str], remote_kv: dict[str, str]) -> DiffResult:
    """Compare local vs remote key/value dicts."""
    local_keys = set(local_kv)
    remote_keys = set(remote_kv)

    added = {k: local_kv[k] for k in local_keys - remote_keys}
    removed = {k: remote_kv[k] for k in remote_keys - local_keys}
    changed = {
        k: (local_kv[k], remote_kv[k])
        for k in local_keys & remote_keys
        if local_kv[k] != remote_kv[k]
    }
    return DiffResult(added=added, removed=removed, changed=changed)


# ---------------------------------------------------------------------------
# Pull
# ---------------------------------------------------------------------------


def pull_env(
    env_cfg: EnvConfig,
    root: Path,
) -> tuple[dict[str, str], dict[str, LockEntry]]:
    """Fetch all secrets for *env_cfg*, merge, and return (merged_kv, lock_entries)."""
    merged: dict[str, str] = {}
    lock_entries: dict[str, LockEntry] = {}

    for secret_ref in env_cfg.secrets:
        raw = fetch_secret_latest(secret_ref.project, secret_ref.secret)

        if secret_ref.type == "raw":
            fmt: SecretFormat = "json"
        else:
            fmt = detect_format(raw, secret_ref.format)

        kv = parse_secret(raw, fmt, secret_ref)

        for key, val in kv.items():
            if key in merged:
                warnings.warn(
                    f"Key collision — '{key}' found in both "
                    f"'{lock_entries[key].secret}' and '{secret_ref.secret}'. "
                    f"Using value from '{secret_ref.secret}' (last wins). "
                    "Check your secret organisation.",
                    KeyCollisionWarning,
                    stacklevel=2,
                )
            merged[key] = val
            lock_entries[key] = LockEntry(
                secret=secret_ref.secret,
                project=secret_ref.project,
                format=fmt if secret_ref.type != "raw" else None,
                type=secret_ref.type,
            )

    return merged, lock_entries


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------


def push_env(
    env_cfg: EnvConfig,
    local_kv: dict[str, str],
    lock_entries: dict[str, LockEntry],
    root: Path,
) -> dict[str, DiffResult]:
    """Push changed keys back to their respective secrets.

    Returns a mapping of secret_name -> DiffResult for reporting.
    """
    # Group local keys by (secret, project)
    groups: dict[tuple[str, str], dict[str, str]] = {}
    for key, val in local_kv.items():
        entry = lock_entries.get(key)
        if entry is None:
            # Key not in lock — shouldn't happen after a pull, skip with warning
            warnings.warn(
                f"Key '{key}' not found in senzu.lock — skipping.",
                stacklevel=2,
            )
            continue
        group_key = (entry.secret, entry.project)
        groups.setdefault(group_key, {})[key] = val

    results: dict[str, DiffResult] = {}

    for (secret_name, project), local_group in groups.items():
        # Determine format from lock
        fmt: SecretFormat = "json"
        for key in local_group:
            entry = lock_entries[key]
            if entry.format is not None:
                fmt = entry.format
                break

        # Fetch remote
        raw_remote = fetch_secret_latest(project, secret_name)
        secret_ref = _find_secret_ref(env_cfg, secret_name, project)
        remote_kv_all = parse_secret(raw_remote, fmt, secret_ref) if secret_ref else {}

        # Only compare keys that belong to this secret
        remote_group = {k: v for k, v in remote_kv_all.items() if k in lock_entries}

        dr = diff_env(local_group, remote_group)
        results[secret_name] = dr

        if not dr.has_drift:
            continue

        # Build new payload — start with remote, apply local changes
        new_kv = dict(remote_kv_all)
        new_kv.update(local_group)
        # Remove keys that were deleted locally (in remote_group but not local_group)
        for k in dr.removed:
            new_kv.pop(k, None)

        payload = serialize_secret(new_kv, fmt)
        push_secret_version(project, secret_name, payload)

    return results


def _find_secret_ref(env_cfg: EnvConfig, secret_name: str, project: str) -> SecretRef | None:
    for ref in env_cfg.secrets:
        if ref.secret == secret_name and ref.project == project:
            return ref
    return None


# ---------------------------------------------------------------------------
# Generate settings.py
# ---------------------------------------------------------------------------


def generate_settings_source(env_name: str, kv: dict[str, str]) -> str:
    """Generate a settings.py snippet from a merged kv dict."""
    lines = [
        f"# Auto-generated by senzu from env '{env_name}' — review before committing.",
        "# Refine types, add defaults, and remove any keys not needed at the app level.",
        "from senzu import SenzuSettings",
        "",
        "",
        "class Settings(SenzuSettings):",
    ]

    for key, val in kv.items():
        field_name = key.lower()
        # Detect nested/raw JSON (single-quoted)
        if val.startswith("'") and val.endswith("'"):
            lines.append(f"    {field_name}: dict  # nested JSON")
        else:
            lines.append(f"    {field_name}: str")

    if len(kv) == 0:
        lines.append("    pass")

    lines.append("")
    return "\n".join(lines)
