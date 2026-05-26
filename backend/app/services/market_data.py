from datetime import datetime, timezone

import yfinance as yf

from app.config import Config
from app.models import MarketSnapshot


def fetch_vix_yfinance(symbol: str = "^VIX") -> float:
    history = yf.Ticker(symbol).history(period="5d")
    if history.empty:
        raise ValueError(f"No VIX data returned for {symbol}")
    return float(history["Close"].dropna().iloc[-1])


def get_market_snapshot(config: Config) -> MarketSnapshot:
    try:
        vix = fetch_vix_yfinance(config.market.vix_symbol)
        return MarketSnapshot(as_of=datetime.now(timezone.utc), vix=vix, source="yfinance")
    except Exception:
        return MarketSnapshot(as_of=datetime.now(timezone.utc), vix=None, source="unavailable")
