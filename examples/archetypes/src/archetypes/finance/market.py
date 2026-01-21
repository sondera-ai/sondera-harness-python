"""Market data tools."""

from typing import Literal

from pydantic import BaseModel


class StockQuote(BaseModel):
    """Stock quote information."""

    symbol: str
    name: str | None = None
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    volume: int | None = None
    aum: str | None = None
    expense_ratio: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    dividend_yield: float | None = None
    pe_ratio: float | None = None
    market_cap: str | None = None
    error: str | None = None


class MarketNewsArticle(BaseModel):
    """A single market news article."""

    headline: str | None = None
    source: str | None = None
    sentiment: Literal["positive", "neutral", "negative"] | None = None
    published: str | None = None
    message: str | None = None


class MarketNewsResponse(BaseModel):
    """Market news response for a symbol."""

    symbol: str
    news: list[MarketNewsArticle]


_QUOTES: dict[str, dict] = {
    "VTI": {
        "symbol": "VTI",
        "name": "Vanguard Total Stock Market ETF",
        "price": 245.30,
        "change": 1.85,
        "change_percent": 0.76,
        "volume": 4567890,
        "aum": "1.7T",
        "expense_ratio": 0.03,
        "day_high": 246.15,
        "day_low": 243.80,
        "dividend_yield": 1.32,
    },
    "BND": {
        "symbol": "BND",
        "name": "Vanguard Total Bond Market ETF",
        "price": 78.45,
        "change": -0.15,
        "change_percent": -0.19,
        "volume": 6789012,
        "aum": "290B",
        "expense_ratio": 0.03,
        "day_high": 78.60,
        "day_low": 78.25,
        "dividend_yield": 4.12,
    },
    "QQQ": {
        "symbol": "QQQ",
        "name": "Invesco QQQ Trust ETF",
        "price": 385.40,
        "change": 4.25,
        "change_percent": 1.12,
        "volume": 45678901,
        "aum": "220B",
        "expense_ratio": 0.20,
        "day_high": 387.90,
        "day_low": 382.15,
        "dividend_yield": 0.65,
    },
    "ARKK": {
        "symbol": "ARKK",
        "name": "ARK Innovation ETF",
        "price": 45.20,
        "change": -1.35,
        "change_percent": -2.90,
        "volume": 12345678,
        "aum": "6.8B",
        "expense_ratio": 0.75,
        "day_high": 46.80,
        "day_low": 44.95,
        "dividend_yield": 0.00,
    },
    "VXUS": {
        "symbol": "VXUS",
        "name": "Vanguard Total International Stock ETF",
        "price": 58.20,
        "change": 0.75,
        "change_percent": 1.31,
        "volume": 3456789,
        "aum": "450B",
        "expense_ratio": 0.08,
        "day_high": 58.45,
        "day_low": 57.85,
        "dividend_yield": 3.25,
    },
    "AAPL": {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "price": 178.50,
        "change": 2.35,
        "change_percent": 1.33,
        "volume": 58234567,
        "market_cap": "2.78T",
        "pe_ratio": 28.5,
        "day_high": 179.20,
        "day_low": 176.80,
    },
    "GOOGL": {
        "symbol": "GOOGL",
        "name": "Alphabet Inc.",
        "price": 142.30,
        "change": -0.85,
        "change_percent": -0.59,
        "volume": 23456789,
        "market_cap": "1.82T",
        "pe_ratio": 25.8,
        "day_high": 143.50,
        "day_low": 141.90,
    },
    "MSFT": {
        "symbol": "MSFT",
        "name": "Microsoft Corporation",
        "price": 415.20,
        "change": 5.60,
        "change_percent": 1.37,
        "volume": 19876543,
        "market_cap": "3.1T",
        "pe_ratio": 35.2,
        "day_high": 417.50,
        "day_low": 412.80,
    },
    "TSLA": {
        "symbol": "TSLA",
        "name": "Tesla Inc.",
        "price": 245.50,
        "change": -8.20,
        "change_percent": -3.23,
        "volume": 98765432,
        "market_cap": "780B",
        "pe_ratio": 62.5,
        "day_high": 252.30,
        "day_low": 243.10,
    },
    "VOO": {
        "symbol": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "price": 455.23,
        "change": 3.45,
        "change_percent": 0.76,
        "volume": 5678901,
        "aum": "950B",
        "expense_ratio": 0.03,
        "day_high": 456.80,
        "day_low": 453.20,
        "dividend_yield": 1.45,
    },
    "VTEB": {
        "symbol": "VTEB",
        "name": "Vanguard Tax-Exempt Bond ETF",
        "price": 52.15,
        "change": -0.08,
        "change_percent": -0.15,
        "volume": 2345678,
        "aum": "95B",
        "expense_ratio": 0.05,
        "day_high": 52.30,
        "day_low": 52.05,
        "dividend_yield": 2.85,
    },
    "VNQ": {
        "symbol": "VNQ",
        "name": "Vanguard Real Estate ETF",
        "price": 89.75,
        "change": 1.20,
        "change_percent": 1.35,
        "volume": 3456789,
        "aum": "45B",
        "expense_ratio": 0.12,
        "day_high": 90.15,
        "day_low": 88.90,
        "dividend_yield": 3.75,
    },
    "SOXX": {
        "symbol": "SOXX",
        "name": "iShares Semiconductor ETF",
        "price": 215.60,
        "change": 3.85,
        "change_percent": 1.82,
        "volume": 8765432,
        "aum": "12B",
        "expense_ratio": 0.35,
        "day_high": 218.20,
        "day_low": 213.40,
        "dividend_yield": 0.95,
    },
    "ICLN": {
        "symbol": "ICLN",
        "name": "iShares Global Clean Energy ETF",
        "price": 18.75,
        "change": -0.45,
        "change_percent": -2.34,
        "volume": 9876543,
        "aum": "4.5B",
        "expense_ratio": 0.42,
        "day_high": 19.35,
        "day_low": 18.60,
        "dividend_yield": 0.55,
    },
    "VEA": {
        "symbol": "VEA",
        "name": "Vanguard FTSE Developed Markets ETF",
        "price": 48.75,
        "change": 0.65,
        "change_percent": 1.35,
        "volume": 4567890,
        "aum": "120B",
        "expense_ratio": 0.05,
        "day_high": 49.10,
        "day_low": 48.40,
        "dividend_yield": 2.95,
    },
}

_NEWS: dict[str, list[dict]] = {
    "VTI": [
        {
            "headline": "U.S. Stock Market Shows Resilience Amid Economic Uncertainty",
            "source": "Wall Street Journal",
            "sentiment": "neutral",
            "published": "2024-12-14",
        },
        {
            "headline": "Broad Market ETFs See Strong Inflows as Investors Seek Diversification",
            "source": "Morningstar",
            "sentiment": "positive",
            "published": "2024-12-13",
        },
    ],
    "BND": [
        {
            "headline": "Bond Markets Rally on Fed Rate Cut Expectations",
            "source": "Bloomberg",
            "sentiment": "positive",
            "published": "2024-12-14",
        },
        {
            "headline": "Fixed Income ETFs Gain Popularity as Yields Stabilize",
            "source": "Financial Times",
            "sentiment": "positive",
            "published": "2024-12-12",
        },
    ],
    "QQQ": [
        {
            "headline": "Tech Stocks Lead Market Recovery on AI Optimism",
            "source": "CNBC",
            "sentiment": "positive",
            "published": "2024-12-14",
        },
        {
            "headline": "Nasdaq 100 ETF Sees Record Weekly Inflows",
            "source": "Reuters",
            "sentiment": "positive",
            "published": "2024-12-13",
        },
    ],
    "AAPL": [
        {
            "headline": "Apple Announces New AI Features for iPhone",
            "source": "TechCrunch",
            "sentiment": "positive",
            "published": "2024-12-14",
        },
        {
            "headline": "Apple Services Revenue Hits Record High",
            "source": "Bloomberg",
            "sentiment": "positive",
            "published": "2024-12-13",
        },
    ],
}


def get_stock_quote(symbol: str) -> StockQuote:
    """Get real-time stock quote and market data for a given symbol.

    Args:
        symbol: Stock symbol (e.g., AAPL, GOOGL, MSFT, VTI)

    Returns:
        Stock quote information including price, change, volume, and more
    """
    quote_data = _QUOTES.get(symbol.upper())
    if quote_data:
        return StockQuote(**quote_data)
    return StockQuote(symbol=symbol.upper(), error=f"Quote not available for {symbol}")


def get_market_news(symbol: str) -> MarketNewsResponse:
    """Get recent market news and sentiment for a given symbol.

    Args:
        symbol: Stock symbol (e.g., AAPL, GOOGL, VTI)

    Returns:
        Recent news articles with headlines, sources, sentiment, and publication dates
    """
    news_list = _NEWS.get(symbol.upper())
    if news_list:
        articles = [MarketNewsArticle(**article) for article in news_list]
    else:
        articles = [MarketNewsArticle(message=f"No recent news for {symbol}")]
    return MarketNewsResponse(symbol=symbol.upper(), news=articles)
