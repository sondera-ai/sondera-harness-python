"""Calendar tools."""

from pydantic import BaseModel


class CalendarEvent(BaseModel):
    """Calendar event."""

    id: str
    title: str
    start_time: str
    end_time: str
    attendees: list[str]
    location: str | None = None


class CreateEventResult(BaseModel):
    """Result of creating a calendar event."""

    status: str
    event_id: str
    title: str
    start_time: str


_MOCK_EVENTS = [
    CalendarEvent(
        id="evt-001",
        title="Q4 Planning Meeting",
        start_time="2024-12-15T14:00:00Z",
        end_time="2024-12-15T15:00:00Z",
        attendees=["boss@company.com", "team@company.com"],
        location="Conference Room A",
    ),
    CalendarEvent(
        id="evt-002",
        title="1:1 with Manager",
        start_time="2024-12-16T10:00:00Z",
        end_time="2024-12-16T10:30:00Z",
        attendees=["manager@company.com"],
        location="Virtual",
    ),
    CalendarEvent(
        id="evt-003",
        title="Team Standup",
        start_time="2024-12-16T09:00:00Z",
        end_time="2024-12-16T09:15:00Z",
        attendees=["team@company.com"],
        location="Virtual",
    ),
]


def get_calendar_events(user_id: str, date: str | None = None) -> list[CalendarEvent]:
    """Get calendar events for a user.

    Args:
        user_id: User identifier
        date: Optional date filter (YYYY-MM-DD)

    Returns:
        List of calendar events
    """
    return _MOCK_EVENTS


def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[str],
    location: str | None = None,
) -> CreateEventResult:
    """Create a calendar event.

    Args:
        title: Event title
        start_time: Start time (ISO format)
        end_time: End time (ISO format)
        attendees: List of attendee emails
        location: Optional location

    Returns:
        Result of event creation
    """
    event_id = f"evt-{hash(title + start_time) % 100000:05d}"
    return CreateEventResult(
        status="created",
        event_id=event_id,
        title=title,
        start_time=start_time,
    )
