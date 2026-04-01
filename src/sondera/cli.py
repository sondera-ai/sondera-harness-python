"""The Sondera Harness CLI and TUI entrypoints."""

import click
from click_default_group import DefaultGroup

from sondera.tui.app import SonderaApp


@click.group(cls=DefaultGroup, default="default", default_if_no_args=True)
def cli() -> None:
    """A CLI and TUI for interacting with the Sondera Harness SDK and Harness Service."""


@cli.command()
def default() -> None:
    """Launch the Sondera Harness TUI."""
    app = SonderaApp()
    app.run()


@cli.group()
def auth() -> None:
    """Authentication commands."""


@auth.command()
@click.option(
    "--url",
    "base_url",
    default=None,
    help="Base URL of the Sondera web app (auto-detected by default)",
)
def login(base_url: str | None) -> None:
    """Authenticate with Sondera via browser.

    Opens your browser to sign in, then automatically saves your
    API token to ~/.sondera/env.
    """
    from sondera.auth.device import (
        DEFAULT_BASE_URL,
        build_auth_url,
        exchange_token,
        open_browser,
        save_credentials,
        start_callback_server,
        wait_for_callback,
    )

    if base_url is None:
        base_url = DEFAULT_BASE_URL

    # Step 1: Start localhost callback server
    server, port = start_callback_server()

    # Step 2: Open browser to Clerk sign-in (pass port only, not full localhost URL)
    auth_url = build_auth_url(base_url, port)
    click.echo("Opening browser to authenticate...")
    click.echo()

    if not open_browser(auth_url):
        click.echo("Could not open browser automatically.")
        click.echo(f"Please open this URL: {auth_url}")
        click.echo()

    # Step 3: Wait for the callback
    click.echo("Waiting for browser sign-in...", nl=False)
    try:
        session_token = wait_for_callback(server)
    except KeyboardInterrupt:
        click.echo()
        click.echo("Authentication cancelled.")
        raise SystemExit(130) from None
    except TimeoutError:
        click.echo()
        click.echo("Timed out waiting for sign-in. Please try again.")
        raise SystemExit(1) from None
    except Exception as e:
        click.echo()
        click.echo(f"Authentication failed: {e}", err=True)
        raise SystemExit(1) from None
    finally:
        server.server_close()

    click.echo(" done!")

    # Step 4: Exchange session for API key
    try:
        result = exchange_token(base_url, session_token)
    except Exception as e:
        click.echo(f"Error exchanging token: {e}", err=True)
        raise SystemExit(1) from None

    # Step 5: Save credentials
    env_path = save_credentials(result["api_token"], result["endpoint"])

    click.echo()
    click.secho("Successfully authenticated!", fg="green", bold=True)
    click.echo(f"Credentials saved to {env_path}")
    click.echo()
    click.echo("You can now use the Sondera CLI and TUI:")
    click.echo("  sondera          # Launch the TUI")
    click.echo("  sondera --help   # See all commands")


if __name__ == "__main__":
    cli()
