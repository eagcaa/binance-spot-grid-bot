"""Public, read-only Binance Spot symbol trading filters.

Current exchangeInfo rules are used as a proxy for the historical test period.
They are NOT guaranteed to be the rules in force on each historical date.
"""
import json
from decimal import Decimal as D
from urllib.parse import urlencode
from urllib.request import urlopen


def read_symbol_rules(symbol, *, base_url="https://api.binance.com"):
    if not symbol or not symbol.isalnum():
        raise ValueError("invalid symbol")
    query = urlencode({"symbol": symbol.upper()})
    with urlopen(f"{base_url.rstrip('/')}/api/v3/exchangeInfo?{query}", timeout=20) as response:
        data = json.load(response)
    symbols = data.get("symbols") if isinstance(data, dict) else None
    if not isinstance(symbols, list) or len(symbols) != 1:
        raise ValueError(f"missing or ambiguous Binance rules for {symbol}")
    record = symbols[0]
    if record.get("symbol") != symbol.upper():
        raise ValueError(f"unexpected Binance symbol for {symbol}")
    if record.get("status") != "TRADING" or not record.get("isSpotTradingAllowed", True):
        raise ValueError(f"symbol not available for spot trading: {symbol}")
    filters = {f["filterType"]: f for f in record.get("filters", [])}
    try:
        tick = D(filters["PRICE_FILTER"]["tickSize"])
        qty_step = D(filters["LOT_SIZE"]["stepSize"])
        notional_filter = filters.get("NOTIONAL") or filters["MIN_NOTIONAL"]
        min_notional = D(notional_filter["minNotional"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"incomplete Binance symbol filters for {symbol}") from exc
    if not (tick.is_finite() and qty_step.is_finite() and min_notional.is_finite()
            and tick > 0 and qty_step > 0 and min_notional > 0):
        raise ValueError(f"invalid Binance symbol filters for {symbol}")
    return {"tick": tick, "qty_step": qty_step, "min_notional": min_notional}
