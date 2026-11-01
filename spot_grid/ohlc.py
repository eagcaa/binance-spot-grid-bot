"""OHLC replay with explicit intrabar-path assumptions (not exchange fills)."""
import csv
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from .engine import GridConfig, GridEngine


def read_ohlc(path):
    with open(path, newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"open", "high", "low", "close"}.issubset(reader.fieldnames):
            raise ValueError("OHLC CSV needs open,high,low,close columns")
        candles = []
        previous_time = None
        time_column = next((name for name in ("open_time", "timestamp", "time")
                            if name in reader.fieldnames), None)
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
            if time_column:
                raw_time = row.get(time_column, "")
                try:
                    if raw_time.isdigit():
                        numeric = int(raw_time)
                        # Binance open_time is usually milliseconds.
                        stamp = datetime.fromtimestamp(
                            numeric / (1000 if numeric > 100000000000 else 1),
                            tz=timezone.utc)
                    else:
                        stamp = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                        if stamp.tzinfo is None:
                            raise ValueError("timestamp needs timezone")
                except (ValueError, OverflowError, OSError) as exc:
                    raise ValueError(f"invalid timestamp at row {number}") from exc
                if previous_time is not None and stamp <= previous_time:
                    raise ValueError(f"timestamps must strictly increase at row {number}")
                previous_time = stamp
                candle["time"] = stamp.isoformat()
            candles.append(candle)
    if not candles:
        raise ValueError("OHLC CSV has no candles")
    return candles


def replay_ohlc(config: GridConfig, candles, path="high_first", conservative=True):
    if path not in ("high_first", "low_first"):
        raise ValueError("path must be high_first or low_first")
    engine = GridEngine(config)
    for candle in candles:
        engine.on_candle(candle, path=path,
                         allow_same_candle_reentry=not conservative)
    return engine


def compare_paths(config: GridConfig, candles):
    """Two optimistic and two conservative path scenarios."""
    results = {}
    for path in ("high_first", "low_first"):
        results[f"{path}_optimistic_touch"] = replay_ohlc(
            replace(config, fill_model="touch"), candles, path,
            conservative=False).snapshot()
        results[f"{path}_conservative_through"] = replay_ohlc(
            replace(config, fill_model="through"), candles, path,
            conservative=True).snapshot()
    return results
