from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

from .config import EnvConfig, SecretRef, SenzuConfig
from .exceptions import (
    KeyCollisionWarning,
    SecretFetchError,
    SecretFormatError,
    SecretPushError,
)
from .lock import LockData, LockEntry

# ---------------------------------------------------------------------------
# GCP Secret Manager client
# ---------------------------------------------------------------------------


def _get_secret_client():
    from google.cloud import secretmanager  # type: ignore

    return secretmanager.SecretManagerServiceClient()


def fetch_secret_latest(project: str, secret_name: str) -> bytes:
    """Return the latest version payload bytes for *secret_name* in *project*."""
    try:
        client = _get_secret_client()
        name = f"projects/{project}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data
    except Exception as exc:
        raise SecretFetchError(
            f"Failed to fetch secret '{secret_name}' from project '{project}': {exc}"
        ) from exc


def push_secret_version(project: str, secret_name: str, payload: bytes) -> None:
    """Add a new version to *secret_name* in *project*."""
    try:
        client = _get_secret_client()
        parent = f"projects/{project}/secrets/{secret_name}"
        client.add_secret_version(
            request={"parent": parent, "payload": {"data": payload}}
        )
    except Exception as exc:
        raise SecretPushError(
            f"Failed to push secret '{secret_name}' to project '{project}': {exc}"
        ) from exc


def ensure_secret_exists(project: str, secret_name: str) -> None:
    """Create the secret resource if it doesn't already exist."""
    try:
        client = _get_secret_client()
        client.create_secret(
            request={
                "parent": f"projects/{project}",
                "secret_id": secret_name,
                "secret": {"replication": {"automatic": {}}},
            }
        )
    except Exception as exc:
        if "already exists" in str(exc).lower() or "409" in str(exc):
            return
        raise SecretPushError(
            f"Failed to create secret '{secret_name}' in project '{project}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Format detection & parsing
# ---------------------------------------------------------------------------

SecretFormat = Literal["json", "dotenv"]


def detect_format(raw: bytes, hint: str | None = None) -> SecretFormat:
    """Return 'json' or 'dotenv'.  *hint* is the user-pinned format if any."""
    if hint is not None:
        return hint  # type: ignore[return-value]
    text = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return "json"
    except json.JSONDecodeError:
        pass
    # Try dotenv — if every non-comment line is KEY=value-ish we accept it
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if all("=" in l for l in lines):
        return "dotenv"
    raise SecretFormatError(
        "Could not auto-detect secret format (tried JSON and dotenv). "
        "Pin it explicitly with `format = \"json\"` or `format = \"dotenv\"` in senzu.toml."
    )


def parse_secret(
    raw: bytes,
    fmt: SecretFormat,
    secret_ref: SecretRef,
) -> dict[str, str]:
    """Parse *raw* bytes into a flat {KEY: value_str} dict.

    For type='raw', returns {env_var: single-quoted JSON string}.
    For JSON format: flat strings kept as-is; nested objects JSON-serialized and single-quoted.
    For dotenv format: parsed via python-dotenv.
    """
    text = raw.decode("utf-8", errors="replace")

    if secret_ref.type == "raw":
        # Whole secret is one value — store as single-quoted JSON string
        env_var = secret_ref.env_var
        assert env_var is not None  # validated in config loading
        # Validate it's valid JSON (warn otherwise)
        try:
            obj = json.loads(text)
            value = "'" + json.dumps(obj, separators=(",", ":")) + "'"
        except json.JSONDecodeError:
            value = text  # store raw if not JSON
        return {env_var: value}

    if fmt == "json":
        data = json.loads(text)
        result: dict[str, str] = {}
        for key, val in data.items():
            if isinstance(val, (dict, list)):
                result[key] = "'" + json.dumps(val, separators=(",", ":")) + "'"
            else:
                result[key] = str(val)
        return result

    # dotenv
    parsed = dotenv_values(stream=__import__("io").StringIO(text))
    return {k: v or "" for k, v in parsed.items()}


def serialize_secret(kv: dict[str, str], fmt: SecretFormat) -> bytes:
    """Serialize a flat {KEY: value} dict back to bytes for Secret Manager."""
    if fmt == "json":
        # Deserialize single-quoted JSON strings back to objects
        out: dict = {}
        for key, val in kv.items():
            if val.startswith("'") and val.endswith("'"):
                inner = val[1:-1]
                try:
                    out[key] = json.loads(inner)
                    continue
                except json.JSONDecodeError:
                    pass
            out[key] = val
        return json.dumps(out, indent=2).encode()

    # dotenv
    lines = []
    for key, val in kv.items():
        # Quote values that contain spaces or special chars
        if " " in val or "#" in val or "\n" in val:
            val = f'"{val}"'
        lines.append(f"{key}={val}")
    return "\n".join(lines).encode()


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
# Diff
# ---------------------------------------------------------------------------


class DiffResult:
    __slots__ = ("added", "removed", "changed")

    def __init__(
        self,
        added: dict[str, str],
        removed: dict[str, str],
        changed: dict[str, tuple[str, str]],
    ):
        self.added = added        # keys only in local
        self.removed = removed    # keys only in remote
        self.changed = changed    # keys in both but value differs: {key: (local, remote)}

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
                f"Key '{key}' not found in .senzu.lock — skipping.",
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
        # For raw secrets, parse differently
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
