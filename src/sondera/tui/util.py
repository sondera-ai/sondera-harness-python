"""Shared helpers for Sondera TUI widgets."""

from __future__ import annotations

from datetime import UTC, datetime


def _utc_seconds_ago(dt: datetime) -> int:
    """Return whole seconds elapsed since *dt*.

    Naive datetimes are assumed to be **local time** and converted to
    UTC before comparison.  Aware datetimes are used as-is.
    """
    now = datetime.now(tz=UTC)
    if dt.tzinfo is None:
        # Treat naive datetimes as local time → convert to UTC
        dt = dt.astimezone(UTC)
    return int((now - dt).total_seconds())


def relative_time(dt: datetime) -> str:
    """Format a datetime as a human-readable relative time string.

    Naive datetimes are assumed to be local time.
    """
    seconds = _utc_seconds_ago(dt)
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 172800:
        return "yesterday"
    return f"{seconds // 86400}d ago"
