"""Communications domain - email, calendar, and notification tools."""

from archetypes.communications.calendar import (
    CalendarEvent,
    CreateEventResult,
    create_calendar_event,
    get_calendar_events,
)
from archetypes.communications.email import (
    Email,
    SendEmailResult,
    get_unread_emails,
    send_email,
)

__all__ = [
    "Email",
    "get_unread_emails",
    "SendEmailResult",
    "send_email",
    "CalendarEvent",
    "get_calendar_events",
    "CreateEventResult",
    "create_calendar_event",
]
