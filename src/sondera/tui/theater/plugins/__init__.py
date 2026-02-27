"""Theater visualization plugins."""

from sondera.tui.theater.plugins.ekg import EKGPlugin

# Registry of all available visualization plugins
AVAILABLE_PLUGINS = (EKGPlugin,)

__all__ = [
    "EKGPlugin",
    "AVAILABLE_PLUGINS",
]
