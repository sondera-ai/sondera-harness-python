"""Tests for sondera.config — shared env file utilities.

The Rust update_env_file implementation is tested by 34 unit tests in env.rs.
These tests verify the Python wrapper wiring and import chain.
"""

import os
from pathlib import Path
from unittest.mock import patch


def _make_mock_rs_update_env_file(home_dir: Path):
    """Create a mock Rust update_env_file that operates on a temp directory."""

    def mock_update_env_file(updates: dict) -> str:
        env_path = home_dir / ".sondera" / "env"
        env_path.parent.mkdir(parents=True, exist_ok=True)

        existing = ""
        if env_path.exists():
            existing = env_path.read_text()

        seen_keys: set[str] = set()
        new_lines: list[str] = []

        for line in existing.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            key_part = stripped
            if key_part.startswith("export "):
                key_part = key_part[len("export ") :].lstrip()
            if "=" in key_part:
                key = key_part.split("=", 1)[0].strip()
                if key in updates:
                    seen_keys.add(key)
                    if updates[key] is not None:
                        new_lines.append(f"{key}={updates[key]}")
                    continue
            new_lines.append(line)

        for key, value in updates.items():
            if key not in seen_keys and value is not None:
                new_lines.append(f"{key}={value}")

        content = "\n".join(new_lines) + "\n"
        fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)

        return str(env_path)

    return mock_update_env_file


class TestUpdateEnvFile:
    """Tests for update_env_file() — Python wrapper over Rust binding."""

    def test_creates_file_and_returns_path(self, tmp_path):
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera_harness_client.update_env_file",
            side_effect=mock_fn,
            create=True,
        ):
            from sondera.config import update_env_file

            result = update_env_file({"KEY": "value"})

        env_file = tmp_path / ".sondera" / "env"
        assert result == env_file
        assert env_file.exists()
        assert "KEY=value" in env_file.read_text()

    def test_preserves_comments(self, tmp_path):
        env_file = tmp_path / ".sondera" / "env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("# comment\nA=1\n")
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera_harness_client.update_env_file",
            side_effect=mock_fn,
            create=True,
        ):
            from sondera.config import update_env_file

            update_env_file({"A": "2"})

        lines = env_file.read_text().splitlines()
        assert lines[0] == "# comment"
        assert lines[1] == "A=2"

    def test_removes_key_when_none(self, tmp_path):
        env_file = tmp_path / ".sondera" / "env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("KEEP=yes\nREMOVE=bye\n")
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera_harness_client.update_env_file",
            side_effect=mock_fn,
            create=True,
        ):
            from sondera.config import update_env_file

            update_env_file({"REMOVE": None})

        content = env_file.read_text()
        assert "KEEP=yes" in content
        assert "REMOVE" not in content

    def test_sets_restrictive_permissions(self, tmp_path):
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera_harness_client.update_env_file",
            side_effect=mock_fn,
            create=True,
        ):
            from sondera.config import update_env_file

            update_env_file({"KEY": "val"})

        env_file = tmp_path / ".sondera" / "env"
        mode = env_file.stat().st_mode & 0o777
        assert mode == 0o600
