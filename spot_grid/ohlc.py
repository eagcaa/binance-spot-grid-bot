"""OHLC replay with explicit intrabar-path assumptions (not exchange fills)."""
import csv
from decimal import Decimal

from .engine import GridConfig, GridEngine


def read_ohlc(path):
    with open(path, newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"open", "high", "low", "close"}.issubset(reader.fieldnames):
            raise ValueError("OHLC CSV needs open,high,low,close columns")
        candles = []
        for number, row in enumerate(reader, 2):
            try:
                candle = {key: Decimal(row[key]) for key in ("open", "high", "low", "close")}
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"invalid OHLC values at CSV row {number}") from exc
            o, h, l, c = (candle[k] for k in ("open", "high", "low", "close"))
            if not all(x.is_finite() and x > 0 for x in (o, h, l, c)):
                raise ValueError(f"non-positive or non-finite OHLC at row {number}")
            if l > min(o, c) or h < max(o, c) or l > h:
                raise ValueError(f"inconsistent OHLC at row {number}")
            candles.append(candle)
    if not candles:
        raise ValueError("OHLC CSV has no candles")
    return candles


def replay_ohlc(config: GridConfig, candles, path="high_first"):
    if path not in ("high_first", "low_first"):
        raise ValueError("path must be high_first or low_first")
    engine = GridEngine(config)
    for candle in candles:
        if path == "high_first":
            points = (candle["open"], candle["high"], candle["low"], candle["close"])
        else:
            points = (candle["open"], candle["low"], candle["high"], candle["close"])
        for price in points:
            engine.on_price(price)
    return engine


def compare_paths(config: GridConfig, candles):
    return {
        path: replay_ohlc(config, candles, path).snapshot()
        for path in ("high_first", "low_first")
    }
