"""Tests for sondera.pydantic.analyze."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from sondera.pydantic.analyze import discover_tool_definitions


def test_discover_warns_when_toolset_exposes_neither_attribute(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Issue 6 regression: a toolset with neither tool_defs nor tools must
    log a warning rather than silently dropping its tools from the agent card.
    """

    class _OpaqueToolset:
        # No tool_defs, no tools -- discover_tool_definitions used to silently
        # skip these toolsets. The new behaviour logs a warning.
        pass

    agent = MagicMock()
    agent.toolsets = [_OpaqueToolset()]

    with caplog.at_level(logging.WARNING, logger="sondera.pydantic.analyze"):
        result = discover_tool_definitions(agent)

    assert result == []
    assert any(
        "_OpaqueToolset" in record.getMessage() and "neither" in record.getMessage()
        for record in caplog.records
    )
