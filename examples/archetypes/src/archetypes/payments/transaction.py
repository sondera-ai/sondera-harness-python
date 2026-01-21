"""Transaction tools."""

from pydantic import BaseModel


class Transaction(BaseModel):
    """Transaction information."""

    transaction_id: str
    merchant_name: str
    amount: float


def get_transactions(customer_id: str, amount: float) -> list[Transaction]:
    """Return transaction history for a customer filtered by amount.

    Args:
        customer_id: Customer identifier
        amount: Transaction amount to filter

    Returns:
        List of transactions matching the criteria
    """
    return [
        Transaction(
            transaction_id="001", merchant_name="MerchantX", amount=float(amount)
        ),
        Transaction(
            transaction_id="002", merchant_name="MerchantX", amount=float(amount)
        ),
    ]
