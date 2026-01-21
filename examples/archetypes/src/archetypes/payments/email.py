"""Email tools for payments domain."""

from pydantic import BaseModel


class EmailStatus(BaseModel):
    """Email sending status."""

    status: str
    to: str
    subject: str
    body: str


def send_email(to: str, subject: str, body: str) -> EmailStatus:
    """Send an email to a recipient.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content

    Returns:
        Status of email sending operation
    """
    return EmailStatus(status="ok", to=to, subject=subject, body=body)
