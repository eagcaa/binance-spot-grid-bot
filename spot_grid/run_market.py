"""Read-only market evaluation CLI.

Example:
  DATABASE_URL='postgresql://readonly:...@host/db' python -m spot_grid.run_market \
    --symbol BTCUSDT --start 2026-08-01T00:00:00+00:00 \
    --end 2026-10-01T00:00:00+00:00 --horizon-minutes 1440
"""
import argparse
import os
from datetime import datetime
from decimal import Decimal as D

from .binance_reader import read_binance_candles
from .forecast_reader import load_forecasts
from .strategy import evaluate_strategy


INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
AUTO_INTERVALS = {15: "1m", 60: "5m", 240: "15m", 1440: "1h"}


def select_interval(horizon_minutes, requested="auto"):
    if horizon_minutes <= 0:
        raise ValueError("horizon must be positive")
    interval = (AUTO_INTERVALS.get(horizon_minutes)
                if requested == "auto" else requested)
    if interval not in INTERVAL_MINUTES:
        raise ValueError("unsupported horizon or candle interval")
    if horizon_minutes // INTERVAL_MINUTES[interval] < 10:
        raise ValueError("at least 10 candles per forecast horizon required")
    return interval


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Binance spot grid comparison")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--end", type=datetime.fromisoformat, required=True)
    parser.add_argument("--horizon-minutes", type=int, required=True)
    parser.add_argument("--interval", default="auto")
    parser.add_argument("--capital", type=D, default=D("1000"))
    parser.add_argument("--min-samples", type=int, default=30)
    args = parser.parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("DATABASE_URL must point to a read-only PostgreSQL account")
    interval = select_interval(args.horizon_minutes, args.interval)
    forecasts, outcomes = load_forecasts(
        dsn, symbol=args.symbol, start=args.start, end=args.end)
    forecasts = [f for f in forecasts if f.horizon_minutes == args.horizon_minutes]
    candles = read_binance_candles(args.symbol, start=args.start,
                                   end=args.end, interval=interval)
    report = evaluate_strategy(forecasts, candles, outcomes,
                               capital=args.capital, min_samples=args.min_samples)
    print(f"Symbol: {args.symbol} | windows: {report['total_windows']} | traded: {report['traded_windows']}")
    print("Strategy       Total PNL       Avg PNL        Win rate       Worst")
    for key in ("forecast", "classic", "buy_hold", "forecast_traded_only"):
        item = report["summary"][key]
        print(f"{key:18} {item['total_pnl']:>12} {str(item['average_pnl']):>14} "
              f"{str(item['win_rate']):>14} {str(item['worst_window_pnl']):>12}")
    print("Forecast beat classic:", report["summary"]["forecast_beats_classic_windows"])
    print("Skipped:", report["skip_reasons"])
    print("Classic:", report["classic_definition"])
    print("Valuation:", report["terminal_valuation"])
    return report


if __name__ == "__main__":
    main()
