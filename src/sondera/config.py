"""Shared configuration file utilities.

Delegates to the Rust ``update_env_file`` binding when available (atomic
writes, 0o600 permissions, symlink-safe).  Falls back to a pure-Python
implementation for older ``sondera-harness-client`` builds that lack the
binding.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_PATH = Path("~/.sondera/env").expanduser()


def update_env_file(updates: dict[str, str | None]) -> Path:
    """Update keys in ``~/.sondera/env``, preserving comments, blanks, and ordering.

    Keys mapped to ``None`` are removed; keys mapped to a string are set or
    overwritten. New keys are appended at the end.

    Returns the path to the updated file.
    """
    try:
        from sondera_harness_client import (
            update_env_file as _rs,  # type: ignore[attr-defined]
        )

        return Path(_rs(updates))
    except (ImportError, AttributeError):
        return _update_env_file_py(updates)


def _update_env_file_py(updates: dict[str, str | None]) -> Path:
    """Pure-Python fallback for structure-preserving env file updates."""
    env_path = _ENV_PATH.resolve() if _ENV_PATH.is_symlink() else _ENV_PATH
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        # Handle export prefix
        key_part = stripped
        if key_part.startswith("export "):
            key_part = key_part[len("export ") :].lstrip()
        if "=" in key_part:
            key = key_part.split("=", 1)[0].strip()
            if key in updates:
                updated_keys.add(key)
                if updates[key] is not None:
                    new_lines.append(f"{key}={updates[key]}")
                continue  # Remove if None
        new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys and value is not None:
            new_lines.append(f"{key}={value}")

    content = "\n".join(new_lines) + "\n"

    # Write with 0o600 permissions
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)

    return env_path
