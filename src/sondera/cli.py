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


if __name__ == "__main__":
    cli()
