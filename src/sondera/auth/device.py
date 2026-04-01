"""PKCE authorization flow for Sondera CLI authentication.

Uses a localhost callback server to receive the Clerk session after
browser sign-in, then exchanges it for an API key via the server.
"""

from __future__ import annotations

import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

DEFAULT_BASE_URL = "https://app.sondera.ai"

_ENV_PATH = Path("~/.sondera/env").expanduser()


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the Clerk session token from the redirect."""

    session_token: str | None = None
    error: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        token = params.get("__clerk_session", [None])[0]
        err = params.get("error", [None])[0]

        if err:
            _CallbackHandler.error = err
            self._respond(
                400,
                "Authorization failed. You can close this tab and try again.",
            )
        elif token:
            _CallbackHandler.session_token = token
            self._respond(
                200,
                "Authenticated! You can close this tab and return to your terminal.",
            )
        else:
            self._respond(400, "Missing session token. Please try again.")

    def _respond(self, status: int, message: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        html = f"<html><body><h2>{message}</h2></body></html>"
        self.wfile.write(html.encode())

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # Suppress request logs


def start_callback_server() -> tuple[HTTPServer, int]:
    """Start a localhost HTTP server on a random port.

    Returns (server, port). The server should be shut down after use.
    """
    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    port = server.server_address[1]
    return server, port


def _normalize_url(url: str) -> str:
    """Ensure URL has an https:// scheme."""
    lower = url.lower()
    if not lower.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip("/")


def build_auth_url(base_url: str, port: int) -> str:
    """Build the sign-in URL with cli_port param.

    The sign-in page constructs the localhost redirect client-side,
    avoiding WAF false-positives from localhost URLs in query strings.
    """
    base_url = _normalize_url(base_url)
    return f"{base_url}/sign-in?cli_port={port}"


def wait_for_callback(server: HTTPServer, timeout: float = 120) -> str:
    """Wait for the browser callback with the session token.

    Returns the session token string.
    Raises TimeoutError if no callback received within timeout.
    """
    _CallbackHandler.session_token = None
    _CallbackHandler.error = None

    timer = threading.Timer(timeout, server.shutdown)
    timer.daemon = True
    timer.start()

    try:
        server.handle_request()
    finally:
        timer.cancel()

    if _CallbackHandler.error:
        from sondera.exceptions import AuthenticationError

        raise AuthenticationError(f"Authorization failed: {_CallbackHandler.error}")

    if not _CallbackHandler.session_token:
        raise TimeoutError("No callback received — authorization timed out")

    return _CallbackHandler.session_token


def exchange_token(base_url: str, session_token: str) -> dict:
    """Exchange a Clerk session token for an API key.

    POST /api/auth/cli/exchange
    Returns: {api_token, endpoint}
    """
    base_url = _normalize_url(base_url)
    with httpx.Client(timeout=10) as client:
        resp = client.post(
            f"{base_url}/api/auth/cli/exchange",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        resp.raise_for_status()
        return resp.json()


def save_credentials(token: str, endpoint: str) -> Path:
    """Save API token and endpoint to ~/.sondera/env.

    Creates/updates the env file, preserving any existing variables
    that aren't being overwritten.

    Returns the path to the env file.
    """
    env_path = _ENV_PATH
    env_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing env file if it exists
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()

    # Update with new values
    existing["SONDERA_API_TOKEN"] = token
    existing["SONDERA_HARNESS_ENDPOINT"] = endpoint

    # Write back
    lines = [f"{key}={value}" for key, value in sorted(existing.items())]
    # Create the file with owner-only permissions.
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as env_file:
        env_file.write("\n".join(lines) + "\n")

    return env_path


def open_browser(url: str) -> bool:
    """Attempt to open URL in browser. Returns True if successful."""
    try:
        return webbrowser.open(url)
    except Exception:
        return False
