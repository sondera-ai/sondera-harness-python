"""Refund tools."""

from pydantic import BaseModel


class RefundStatus(BaseModel):
    """Refund operation status."""

    status: str
    transaction_id: str
    refunded_amount: float


def initiate_refund(transaction_id: str, amount: float) -> RefundStatus:
    """Initiate a refund for a transaction.

    Args:
        transaction_id: Transaction to refund
        amount: Amount to refund

    Returns:
        Status of refund operation
    """
    return RefundStatus(
        status="ok",
        transaction_id=transaction_id,
        refunded_amount=float(amount),
    )
