"""Tests for PKCE authorization flow."""

import http.client
import importlib
import sys
import threading
import types
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_sondera_import(monkeypatch):
    """Prevent full sondera package initialization during test collection.

    We need to import sondera.auth.device without triggering sondera/__init__.py
    which pulls in the full harness module tree. We do this by temporarily
    injecting a stub for sondera so submodule imports work independently.
    """
    for name in list(sys.modules):
        if name == "sondera" or name.startswith("sondera."):
            monkeypatch.delitem(sys.modules, name, raising=False)

    src_dir = Path(__file__).resolve().parents[1] / "src" / "sondera"

    sondera_mod = types.ModuleType("sondera")
    sondera_mod.__path__ = [str(src_dir)]

    auth_mod = types.ModuleType("sondera.auth")
    auth_mod.__path__ = [str(src_dir / "auth")]

    config_mod = types.ModuleType("sondera.config")

    def _missing_update_env_file(_updates: dict) -> Path:
        raise AssertionError("test must patch sondera.config.update_env_file")

    config_mod.update_env_file = _missing_update_env_file
    sondera_mod.auth = auth_mod
    sondera_mod.config = config_mod

    monkeypatch.setitem(sys.modules, "sondera", sondera_mod)
    monkeypatch.setitem(sys.modules, "sondera.auth", auth_mod)
    monkeypatch.setitem(sys.modules, "sondera.config", config_mod)


# Import the specific module to avoid triggering sondera.__init__'s heavy imports.
# We import the module directly rather than through the package.
@pytest.fixture()
def device_module():
    """Import sondera.auth.device without triggering the full package init."""
    return importlib.import_module("sondera.auth.device")


def _make_mock_rs_update_env_file(home_dir: Path):
    """Create a mock Rust update_env_file that operates on a temp directory."""
    import os

    def mock_update_env_file(updates: dict) -> str:
        env_path = home_dir / ".sondera" / "env"
        env_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing content
        existing = ""
        if env_path.exists():
            existing = env_path.read_text()

        # Process lines preserving comments, blanks, ordering
        seen_keys: set[str] = set()
        new_lines: list[str] = []

        for line in existing.splitlines():
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
                    seen_keys.add(key)
                    if updates[key] is not None:
                        new_lines.append(f"{key}={updates[key]}")
                    continue
            new_lines.append(line)

        for key, value in updates.items():
            if key not in seen_keys and value is not None:
                new_lines.append(f"{key}={value}")

        content = "\n".join(new_lines) + "\n"

        # Atomic-ish write with 0o600 permissions
        fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)

        return str(env_path)

    return mock_update_env_file


class TestSaveCredentials:
    """Tests for save_credentials() — delegates to Rust update_env_file.

    The Rust implementation is tested by 34 unit tests in env.rs.
    These tests verify the Python wiring and integration.
    """

    def test_creates_new_env_file(self, tmp_path):
        """Should create env file with token and endpoint."""
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera.config.update_env_file",
            side_effect=lambda u: Path(mock_fn(u)),
        ):
            from sondera.auth.device import save_credentials

            result = save_credentials("test-token-123", "harness.sondera.ai")

        env_file = tmp_path / ".sondera" / "env"
        assert result == env_file
        content = env_file.read_text()
        assert "SONDERA_API_TOKEN=test-token-123" in content
        assert "SONDERA_HARNESS_ENDPOINT=harness.sondera.ai" in content

    def test_preserves_existing_vars(self, tmp_path):
        """Should preserve unrelated env vars."""
        env_file = tmp_path / ".sondera" / "env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text(
            "OTHER_VAR=keep-me\nSONDERA_API_TOKEN=old-token\n"  # pragma: allowlist secret
        )
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera.config.update_env_file",
            side_effect=lambda u: Path(mock_fn(u)),
        ):
            from sondera.auth.device import save_credentials

            save_credentials("new-token", "harness.sondera.ai")

        content = env_file.read_text()
        assert "OTHER_VAR=keep-me" in content
        assert "SONDERA_API_TOKEN=new-token" in content
        assert "old-token" not in content

    def test_creates_parent_directory(self, tmp_path):
        """Should create ~/.sondera/ if it doesn't exist."""
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera.config.update_env_file",
            side_effect=lambda u: Path(mock_fn(u)),
        ):
            from sondera.auth.device import save_credentials

            save_credentials("token", "endpoint")

        env_file = tmp_path / ".sondera" / "env"
        assert env_file.exists()

    def test_sets_restrictive_permissions(self, tmp_path):
        """Should set 600 permissions on env file."""
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera.config.update_env_file",
            side_effect=lambda u: Path(mock_fn(u)),
        ):
            from sondera.auth.device import save_credentials

            save_credentials("token", "endpoint")

        env_file = tmp_path / ".sondera" / "env"
        mode = env_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_preserves_comments(self, tmp_path):
        """Comments in the env file should survive login."""
        env_file = tmp_path / ".sondera" / "env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text(
            "# API Configuration\nSONDERA_API_TOKEN=old\n# Keep this\nOTHER=val\n"
        )
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera.config.update_env_file",
            side_effect=lambda u: Path(mock_fn(u)),
        ):
            from sondera.auth.device import save_credentials

            save_credentials("new", "endpoint")

        content = env_file.read_text()
        lines = content.splitlines()
        assert lines[0] == "# API Configuration"
        assert lines[1] == "SONDERA_API_TOKEN=new"
        assert lines[2] == "# Keep this"
        assert lines[3] == "OTHER=val"

    def test_preserves_blank_lines(self, tmp_path):
        """Blank lines should survive login."""
        env_file = tmp_path / ".sondera" / "env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("A=1\n\nB=2\n\nSONDERA_API_TOKEN=old\n")
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera.config.update_env_file",
            side_effect=lambda u: Path(mock_fn(u)),
        ):
            from sondera.auth.device import save_credentials

            save_credentials("new", "endpoint")

        content = env_file.read_text()
        lines = content.splitlines()
        assert lines[0] == "A=1"
        assert lines[1] == ""
        assert lines[2] == "B=2"
        assert lines[3] == ""
        assert lines[4] == "SONDERA_API_TOKEN=new"

    def test_preserves_ordering(self, tmp_path):
        """Keys should NOT be sorted alphabetically — order is preserved."""
        env_file = tmp_path / ".sondera" / "env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("Z_VAR=z\nA_VAR=a\nSONDERA_API_TOKEN=old\n")
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera.config.update_env_file",
            side_effect=lambda u: Path(mock_fn(u)),
        ):
            from sondera.auth.device import save_credentials

            save_credentials("new", "endpoint")

        content = env_file.read_text()
        lines = content.splitlines()
        assert lines[0] == "Z_VAR=z"
        assert lines[1] == "A_VAR=a"
        assert lines[2] == "SONDERA_API_TOKEN=new"

    def test_handles_export_prefix(self, tmp_path):
        """export-prefixed keys should be updated, not duplicated."""
        env_file = tmp_path / ".sondera" / "env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("export SONDERA_API_TOKEN=old\nOTHER=val\n")
        mock_fn = _make_mock_rs_update_env_file(tmp_path)
        with patch(
            "sondera.config.update_env_file",
            side_effect=lambda u: Path(mock_fn(u)),
        ):
            from sondera.auth.device import save_credentials

            save_credentials("new", "endpoint")

        content = env_file.read_text()
        assert "SONDERA_API_TOKEN=new" in content
        assert "old" not in content
        assert content.count("SONDERA_API_TOKEN") == 1, "key should appear exactly once"


class TestDefaultBaseUrl:
    """Tests for default base URL."""

    def test_default_base_url(self):
        from sondera.auth.device import DEFAULT_BASE_URL

        assert DEFAULT_BASE_URL == "https://app.sondera.ai"


class TestCallbackServer:
    """Tests for the localhost callback server."""

    def test_starts_on_random_port(self):
        from sondera.auth.device import start_callback_server

        server, port = start_callback_server()
        try:
            assert port > 0
            assert server.server_address == ("127.0.0.1", port)
        finally:
            server.server_close()

    def test_callback_accepts_session_token_param(self):
        from sondera.auth.device import _CallbackHandler, start_callback_server

        _CallbackHandler.session_token = None
        _CallbackHandler.error = None
        server, port = start_callback_server()
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/callback?__session_token=session-token-123")
            resp = conn.getresponse()
            body = resp.read().decode()

            assert resp.status == 200
            assert "Authenticated!" in body
            assert _CallbackHandler.session_token == "session-token-123"  # noqa: S105
            assert _CallbackHandler.error is None
        finally:
            server.server_close()
            thread.join(timeout=5)

    def test_callback_without_session_token_prompts_fresh_auth(self):
        from sondera.auth.device import _CallbackHandler, start_callback_server

        _CallbackHandler.session_token = None
        _CallbackHandler.error = None
        server, port = start_callback_server()
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/callback?stale_token=legacy-token")
            resp = conn.getresponse()
            body = resp.read().decode()

            assert resp.status == 400
            assert "run `sondera auth login` again" in body
            assert _CallbackHandler.session_token is None
            assert _CallbackHandler.error is not None
            assert "session token" in _CallbackHandler.error
        finally:
            server.server_close()
            thread.join(timeout=5)


class TestBuildAuthUrl:
    """Tests for auth URL construction."""

    def test_builds_sign_in_url_with_port(self):
        from sondera.auth.device import build_auth_url

        url = build_auth_url("https://app.sondera.ai", 9999)
        assert url == "https://app.sondera.ai/sign-in?cli_port=9999"

    def test_custom_base_url(self):
        from sondera.auth.device import build_auth_url

        url = build_auth_url("http://localhost:5173", 9999)
        assert url == "http://localhost:5173/sign-in?cli_port=9999"

    def test_adds_https_when_no_scheme(self):
        from sondera.auth.device import build_auth_url

        url = build_auth_url("example.sondera.ai", 9999)
        assert url == "https://example.sondera.ai/sign-in?cli_port=9999"

    def test_strips_trailing_slash(self):
        from sondera.auth.device import build_auth_url

        url = build_auth_url("https://app.sondera.ai/", 9999)
        assert url == "https://app.sondera.ai/sign-in?cli_port=9999"

    def test_preserves_uppercase_scheme(self):
        from sondera.auth.device import build_auth_url

        url = build_auth_url("HTTPS://app.sondera.ai", 9999)
        assert url == "HTTPS://app.sondera.ai/sign-in?cli_port=9999"
