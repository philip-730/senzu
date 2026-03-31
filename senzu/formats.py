from __future__ import annotations

import json
from typing import Literal

from dotenv import dotenv_values

from .config import SecretRef
from .exceptions import SecretFormatError

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
            elif isinstance(val, str):
                # If the string is itself a JSON object/array, single-quote it so
                # it round-trips correctly through .env files (dotenv strips outer quotes).
                try:
                    inner = json.loads(val)
                    if isinstance(inner, (dict, list)):
                        result[key] = "'" + json.dumps(inner, separators=(",", ":")) + "'"
                        continue
                except json.JSONDecodeError:
                    pass
                result[key] = val
            else:
                result[key] = str(val)
        return result

    # dotenv
    parsed = dotenv_values(stream=__import__("io").StringIO(text))
    return {k: v or "" for k, v in parsed.items()}


def serialize_secret(kv: dict[str, str], fmt: SecretFormat) -> bytes:
    """Serialize a flat {KEY: value} dict back to bytes for Secret Manager."""
    if fmt == "json":
        # Deserialize single-quoted JSON strings back to objects.
        # Also handle bare JSON object/array strings (dotenv strips single quotes on read).
        out: dict = {}
        for key, val in kv.items():
            if val.startswith("'") and val.endswith("'"):
                inner = val[1:-1]
                try:
                    out[key] = json.loads(inner)
                    continue
                except json.JSONDecodeError:
                    pass
            # Bare JSON object/array string (single quotes were stripped by dotenv)
            try:
                parsed = json.loads(val)
                if isinstance(parsed, (dict, list)):
                    out[key] = parsed
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
