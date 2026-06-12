"""Local-first provider secrets (v0.9.1).

Keys configured through the UI land in a gitignored JSON file next to the
server (never the database), chmod 0600. Values from this file overlay the
environment when the provider registry is built — the most recent explicit
user action wins. Nothing in this module logs, returns, or echoes a secret.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Providers a user may configure at runtime, and which fields each accepts.
CONFIGURABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "openai": ("api_key", "base_url"),
    "anthropic": ("api_key",),
    "gemini": ("api_key", "base_url"),
    "ollama": ("base_url",),
}


def load_secrets(path: str | Path) -> dict[str, dict[str, str]]:
    file = Path(path)
    if not file.exists():
        return {}
    try:
        data = json.loads(file.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for provider, fields in CONFIGURABLE_FIELDS.items():
        values = data.get(provider)
        if isinstance(values, dict):
            kept = {k: str(v) for k, v in values.items() if k in fields and v}
            if kept:
                out[provider] = kept
    return out


def _write(path: str | Path, secrets: dict[str, dict[str, str]]) -> None:
    file = Path(path)
    file.write_text(json.dumps(secrets, indent=2) + "\n")
    os.chmod(file, 0o600)


def set_provider_secret(path: str | Path, provider: str, values: dict[str, str]) -> None:
    allowed = CONFIGURABLE_FIELDS[provider]
    secrets = load_secrets(path)
    current = secrets.get(provider, {})
    current.update({k: v.strip() for k, v in values.items() if k in allowed and v and v.strip()})
    secrets[provider] = current
    _write(path, secrets)


def clear_provider_secret(path: str | Path, provider: str) -> None:
    secrets = load_secrets(path)
    if provider in secrets:
        del secrets[provider]
        _write(path, secrets)
