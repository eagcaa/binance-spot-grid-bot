"""Public Binance Spot historical candles; no trading endpoints or keys."""
import json
from datetime import datetime, timezone
from decimal import Decimal as D
from urllib.parse import urlencode
from urllib.request import urlopen


def read_binance_candles(symbol, *, start, end, interval="1h",
                         base_url="https://api.binance.com"):
    """Paginate public klines; exclude candles not fully closed by end."""
    if not symbol or not symbol.isalnum():
        raise ValueError("invalid symbol")
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("invalid UTC date range")
    if interval not in {"1m", "5m", "15m", "1h", "4h", "1d"}:
        raise ValueError("unsupported candle interval")
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    candles = []
    while start_ms < end_ms:
        query = urlencode({"symbol": symbol.upper(), "interval": interval,
                           "startTime": start_ms, "endTime": end_ms - 1,
                           "limit": 1000})
        with urlopen(f"{base_url.rstrip('/')}/api/v3/klines?{query}", timeout=20) as response:
            rows = json.load(response)
        if not isinstance(rows, list):
            raise ValueError("unexpected Binance response")
        if not rows:
            break
        for row in rows:
            opened, closed = int(row[0]), int(row[6])
            if opened < start_ms or closed >= end_ms:
                continue
            candles.append({
                "time": datetime.fromtimestamp(opened / 1000, tz=timezone.utc).isoformat(),
                "open": D(str(row[1])), "high": D(str(row[2])),
                "low": D(str(row[3])), "close": D(str(row[4])),
            })
        next_ms = int(rows[-1][0]) + 1
        if next_ms <= start_ms:
            raise ValueError("Binance pagination did not advance")
        start_ms = next_ms
        if len(rows) < 1000:
            break
    return candles
