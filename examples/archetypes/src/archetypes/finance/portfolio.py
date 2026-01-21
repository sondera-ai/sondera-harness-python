"""Portfolio management tools."""

from pydantic import BaseModel


class Holding(BaseModel):
    """A single holding in a portfolio."""

    symbol: str
    shares: float
    current_price: float
    market_value: float
    cost_basis: float
    gain_loss: float


class PortfolioInfo(BaseModel):
    """Portfolio information including holdings and balances."""

    customer_id: str
    account_id: str | None = None
    total_value: float | None = None
    holdings: list[Holding] | None = None
    cash_balance: float | None = None
    error: str | None = None


_PORTFOLIOS = {
    "CUST001": PortfolioInfo(
        customer_id="CUST001",
        account_id="IRA-78910",
        total_value=485750.50,
        holdings=[
            Holding(
                symbol="VTI",
                shares=800,
                current_price=245.30,
                market_value=196240.00,
                cost_basis=220.00,
                gain_loss=20240.00,
            ),
            Holding(
                symbol="BND",
                shares=1500,
                current_price=78.45,
                market_value=117675.00,
                cost_basis=82.00,
                gain_loss=-5325.00,
            ),
            Holding(
                symbol="VXUS",
                shares=600,
                current_price=58.20,
                market_value=34920.00,
                cost_basis=62.50,
                gain_loss=-2580.00,
            ),
            Holding(
                symbol="VTEB",
                shares=1200,
                current_price=52.15,
                market_value=62580.00,
                cost_basis=53.00,
                gain_loss=-1020.00,
            ),
            Holding(
                symbol="VNQ",
                shares=400,
                current_price=89.75,
                market_value=35900.00,
                cost_basis=95.00,
                gain_loss=-2100.00,
            ),
        ],
        cash_balance=38435.50,
    ),
    "CUST002": PortfolioInfo(
        customer_id="CUST002",
        account_id="ROTH-45123",
        total_value=125890.75,
        holdings=[
            Holding(
                symbol="QQQ",
                shares=200,
                current_price=385.40,
                market_value=77080.00,
                cost_basis=320.00,
                gain_loss=13080.00,
            ),
            Holding(
                symbol="ARKK",
                shares=300,
                current_price=45.20,
                market_value=13560.00,
                cost_basis=85.00,
                gain_loss=-11940.00,
            ),
            Holding(
                symbol="ICLN",
                shares=500,
                current_price=18.75,
                market_value=9375.00,
                cost_basis=25.50,
                gain_loss=-3375.00,
            ),
            Holding(
                symbol="SOXX",
                shares=100,
                current_price=215.60,
                market_value=21560.00,
                cost_basis=180.00,
                gain_loss=3560.00,
            ),
        ],
        cash_balance=4315.75,
    ),
}


def get_portfolio(customer_id: str) -> PortfolioInfo:
    """Return the customer's portfolio holdings and current performance.

    Args:
        customer_id: Customer identifier (CUST001, CUST002)

    Returns:
        Portfolio information including holdings, total value, and cash balance
    """
    if customer_id in _PORTFOLIOS:
        return _PORTFOLIOS[customer_id]
    return PortfolioInfo(customer_id=customer_id, error="Customer not found")
