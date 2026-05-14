"""PKCE authorization flow for Sondera CLI authentication.

Uses a localhost callback server to receive the session token after
browser sign-in, then exchanges it for an API key via the server.
"""

from __future__ import annotations

import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

DEFAULT_BASE_URL = "https://app.sondera.ai"
MISSING_AUTH_CALLBACK_MESSAGE = (
    "Missing session token. Return to your terminal and run `sondera auth login` "
    "again after refreshing the sign-in page."
)


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the session token from the browser redirect."""

    session_token: str | None = None
    error: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        token = params.get("__session_token", [None])[0]
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
            _CallbackHandler.error = MISSING_AUTH_CALLBACK_MESSAGE
            self._respond(400, MISSING_AUTH_CALLBACK_MESSAGE)

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
    """Exchange a browser session token for an API key.

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

    Preserves comments, blank lines, and ordering of existing variables.
    Uses atomic writes with 0o600 permissions via the Rust implementation.

    Returns the path to the env file.
    """
    from sondera.config import update_env_file

    return update_env_file(
        {
            "SONDERA_API_TOKEN": token,
            "SONDERA_HARNESS_ENDPOINT": endpoint,
        }
    )


def open_browser(url: str) -> bool:
    """Attempt to open URL in browser. Returns True if successful."""
    try:
        return webbrowser.open(url)
    except Exception:
        return False
