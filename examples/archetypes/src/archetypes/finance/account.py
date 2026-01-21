"""Account management tools."""

from pydantic import BaseModel


class AccountInfo(BaseModel):
    """Customer account information."""

    customer_id: str
    account_id: str | None = None
    account_number: str | None = None
    ssn: str | None = None
    name: str | None = None
    email: str | None = None
    account_type: str | None = None
    risk_tolerance: str | None = None
    investment_objectives: list[str] | None = None
    region: str | None = None
    account_status: str | None = None
    error: str | None = None


_ACCOUNTS = {
    "CUST001": AccountInfo(
        customer_id="CUST001",
        account_id="ACC-78910",
        account_number="****-****-****-7890",
        ssn="***-**-6789",
        name="Jane Smith",
        email="jane.smith@example.com",
        account_type="Individual Brokerage",
        risk_tolerance="Moderate",
        investment_objectives=["Growth", "Income"],
        region="US",
        account_status="Active",
    ),
}


def get_account_info(customer_id: str) -> AccountInfo:
    """Return customer account details including risk tolerance and account type.

    Args:
        customer_id: Customer identifier (CUST001)

    Returns:
        Account information including masked account number, SSN, name, email, etc.
    """
    if customer_id in _ACCOUNTS:
        return _ACCOUNTS[customer_id]
    return AccountInfo(customer_id=customer_id, error="Customer not found")
