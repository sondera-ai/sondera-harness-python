"""Trading tools."""

from pydantic import BaseModel


class TradeRecommendation(BaseModel):
    """Trade recommendation (not execution)."""

    recommendation_id: str
    customer_id: str
    action: str
    symbol: str
    shares: int
    recommended_price: float
    reasoning: str
    risk_score: str
    requires_approval: bool
    status: str
    disclaimer: str


_MARKET_PRICES = {
    "VTI": 245.30,
    "VOO": 455.23,
    "QQQ": 385.40,
    "BND": 78.45,
    "VTEB": 52.15,
    "VXUS": 58.20,
    "VEA": 48.75,
    "VNQ": 89.75,
    "SOXX": 215.60,
    "ICLN": 18.75,
    "ARKK": 45.20,
    "AAPL": 178.50,
    "MSFT": 415.20,
    "GOOGL": 142.30,
    "TSLA": 245.50,
}


def make_trade_recommendation(
    customer_id: str, action: str, symbol: str, shares: int
) -> TradeRecommendation:
    """Generate a trade recommendation based on portfolio and market conditions.

    Args:
        customer_id: Customer identifier
        action: Trade action ("buy" or "sell")
        symbol: Stock symbol to trade
        shares: Number of shares

    Returns:
        Trade recommendation with reasoning, risk score, and disclaimer.
        Note: This only RECOMMENDS trades, does not execute them.
    """
    recommended_price = _MARKET_PRICES.get(symbol.upper(), 100.00)

    if action.lower() == "buy":
        if symbol.upper() in ["BND", "VTEB"]:
            reasoning = f"Given current interest rate environment, adding {symbol} bonds may provide portfolio stability and income diversification."
        elif symbol.upper() in ["VTI", "VOO"]:
            reasoning = f"Broad market exposure through {symbol} aligns with long-term growth objectives and provides diversification."
        elif symbol.upper() in ["ARKK", "ICLN", "SOXX"]:
            reasoning = f"Growth allocation to {symbol} may capture innovation trends, though with higher volatility risk."
        else:
            reasoning = f"Adding {symbol} position may enhance portfolio diversification based on current allocation analysis."
    else:
        reasoning = f"Reducing {symbol} position may be appropriate for rebalancing or risk management purposes."

    return TradeRecommendation(
        recommendation_id=f"REC-{customer_id}-{symbol}-001",
        customer_id=customer_id,
        action=action.upper(),
        symbol=symbol.upper(),
        shares=shares,
        recommended_price=recommended_price,
        reasoning=reasoning,
        risk_score="Medium",
        requires_approval=True,
        status="PENDING_REVIEW",
        disclaimer="This is a recommendation only. All trades require explicit customer approval. Past performance does not guarantee future results.",
    )
