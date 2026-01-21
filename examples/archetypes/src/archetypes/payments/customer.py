"""Customer profile tools."""

from pydantic import BaseModel


class CustomerProfile(BaseModel):
    """Customer profile information."""

    customer_id: str
    region: str
    email: str
    cc_number: str


def get_customer_profile(customer_id: str) -> CustomerProfile:
    """Return a customer profile with region, email, and credit card information.

    Args:
        customer_id: Customer identifier

    Returns:
        Customer profile information including region, email, and credit card details

    Demo IDs:
      - 10a2b3_us: US region customer
      - 10a2b3_eu: EU region customer
    """
    region = "EU" if customer_id == "10a2b3_eu" else "US"
    return CustomerProfile(
        customer_id=customer_id,
        region=region,
        email="jsmith@gmail.com",
        cc_number="4321 1111 1111 1111",
    )
