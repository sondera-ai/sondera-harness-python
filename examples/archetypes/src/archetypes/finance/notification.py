"""Notification tools for finance domain."""

from pydantic import BaseModel


class NotificationStatus(BaseModel):
    """Notification status."""

    status: str
    notification_id: str
    customer_id: str
    subject: str
    message: str
    channel: str = "email"


def send_notification(
    customer_id: str, subject: str, message: str
) -> NotificationStatus:
    """Send a notification or email to the customer.

    Args:
        customer_id: Customer identifier
        subject: Notification subject
        message: Notification message content

    Returns:
        Status of notification sending operation
    """
    return NotificationStatus(
        status="sent",
        notification_id=f"NOTIF-{customer_id}-001",
        customer_id=customer_id,
        subject=subject,
        message=message,
        channel="email",
    )
