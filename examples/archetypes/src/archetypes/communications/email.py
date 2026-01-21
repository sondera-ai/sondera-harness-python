"""Email tools."""

from pydantic import BaseModel


class Email(BaseModel):
    """Email message."""

    id: str
    sender: str
    subject: str
    body: str
    received_at: str


class SendEmailResult(BaseModel):
    """Email sending result."""

    status: str
    message_id: str
    to: str
    subject: str


_MOCK_EMAILS = [
    Email(
        id="email-001",
        sender="boss@company.com",
        subject="Q4 Planning Meeting",
        body="Please review the attached Q4 goals before our meeting tomorrow at 2pm.",
        received_at="2024-12-14T09:30:00Z",
    ),
    Email(
        id="email-002",
        sender="hr@company.com",
        subject="Benefits Enrollment Deadline",
        body="Reminder: Open enrollment ends December 20th. Please submit your selections.",
        received_at="2024-12-14T08:15:00Z",
    ),
    Email(
        id="email-003",
        sender="client@external.com",
        subject="Project Update Request",
        body="Can you send me the latest status report for the Alpha project?",
        received_at="2024-12-13T16:45:00Z",
    ),
]


def get_unread_emails(user_id: str) -> list[Email]:
    """Get unread emails for a user.

    Args:
        user_id: User identifier

    Returns:
        List of unread emails
    """
    return _MOCK_EMAILS


def send_email(to: str, subject: str, body: str) -> SendEmailResult:
    """Send an email.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content

    Returns:
        Status of email sending operation
    """
    return SendEmailResult(
        status="sent",
        message_id=f"msg-{hash(to + subject) % 100000:05d}",
        to=to,
        subject=subject,
    )
