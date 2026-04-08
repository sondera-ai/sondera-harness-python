"""Tests for PKCE authorization flow."""

from unittest.mock import patch

from sondera.auth.device import (
    DEFAULT_BASE_URL,
    build_auth_url,
    save_credentials,
    start_callback_server,
)


class TestSaveCredentials:
    """Tests for save_credentials()."""

    def test_creates_new_env_file(self, tmp_path):
        """Should create env file with token and endpoint."""
        env_file = tmp_path / "env"
        with patch("sondera.auth.device._ENV_PATH", env_file):
            result = save_credentials("test-token-123", "harness.sondera.ai")

        assert result == env_file
        content = env_file.read_text()
        assert "SONDERA_API_TOKEN=test-token-123" in content
        assert "SONDERA_HARNESS_ENDPOINT=harness.sondera.ai" in content

    def test_preserves_existing_vars(self, tmp_path):
        """Should preserve unrelated env vars."""
        env_file = tmp_path / "env"
        env_file.write_text(
            "OTHER_VAR=keep-me\nSONDERA_API_TOKEN=old-token\n"  # pragma: allowlist secret
        )

        with patch("sondera.auth.device._ENV_PATH", env_file):
            save_credentials("new-token", "harness.sondera.ai")

        content = env_file.read_text()
        assert "OTHER_VAR=keep-me" in content
        assert "SONDERA_API_TOKEN=new-token" in content
        assert "old-token" not in content

    def test_creates_parent_directory(self, tmp_path):
        """Should create ~/.sondera/ if it doesn't exist."""
        env_file = tmp_path / "sondera" / "env"
        with patch("sondera.auth.device._ENV_PATH", env_file):
            save_credentials("token", "endpoint")

        assert env_file.exists()

    def test_sets_restrictive_permissions(self, tmp_path):
        """Should set 600 permissions on env file."""
        env_file = tmp_path / "env"
        with patch("sondera.auth.device._ENV_PATH", env_file):
            save_credentials("token", "endpoint")

        mode = env_file.stat().st_mode & 0o777
        assert mode == 0o600


class TestDefaultBaseUrl:
    """Tests for default base URL."""

    def test_default_base_url(self):
        assert DEFAULT_BASE_URL == "https://app.sondera.ai"


class TestCallbackServer:
    """Tests for the localhost callback server."""

    def test_starts_on_random_port(self):
        server, port = start_callback_server()
        try:
            assert port > 0
            assert server.server_address == ("127.0.0.1", port)
        finally:
            server.server_close()


class TestBuildAuthUrl:
    """Tests for auth URL construction."""

    def test_builds_sign_in_url_with_port(self):
        url = build_auth_url("https://app.sondera.ai", 9999)
        assert url == "https://app.sondera.ai/sign-in?cli_port=9999"

    def test_custom_base_url(self):
        url = build_auth_url("http://localhost:5173", 9999)
        assert url == "http://localhost:5173/sign-in?cli_port=9999"

    def test_adds_https_when_no_scheme(self):
        url = build_auth_url("example.sondera.ai", 9999)
        assert url == "https://example.sondera.ai/sign-in?cli_port=9999"

    def test_strips_trailing_slash(self):
        url = build_auth_url("https://app.sondera.ai/", 9999)
        assert url == "https://app.sondera.ai/sign-in?cli_port=9999"

    def test_preserves_uppercase_scheme(self):
        url = build_auth_url("HTTPS://app.sondera.ai", 9999)
        assert url == "HTTPS://app.sondera.ai/sign-in?cli_port=9999"
