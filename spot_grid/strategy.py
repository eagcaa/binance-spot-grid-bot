"""Opt-in quality-gated, paired walk-forward evaluation."""
from collections import Counter
from datetime import datetime
from decimal import Decimal as D

from .comparison import buy_hold
from .engine import GridEngine
from .planner import plan_auto
from .quality import coverage_at


def evaluate_strategy(forecasts, candles, outcomes, *, horizon,
                      capital=D("1000"), target=D("0.80"), min_samples=30,
                      max_intervals=50, classic_half_width=D("0.05"),
                      **grid_options):
    """Independent windows, no reinvestment. Classic band is fixed ex ante.

    All candle timestamps are UTC-offset-aware. Outcomes must have evaluation
    timestamps strictly earlier than the first candle of each window.
    """
    if not (D(0) < classic_half_width < D(1)):
        raise ValueError("classic_half_width must be between zero and one")
    parsed = []
    for candle in candles:
        stamp = datetime.fromisoformat(candle["time"].replace("Z", "+00:00"))
        if stamp.tzinfo is None or (parsed and stamp <= parsed[-1][0]):
            raise ValueError("candles must be strictly increasing and timezone-aware")
        parsed.append((stamp, candle))
    results = []
    previous_end = None
    grid_options.setdefault("fill_model", "through")
    for forecast in sorted(forecasts, key=lambda f: f.created_at):
        if previous_end is not None and forecast.created_at < previous_end:
            continue
        window = [(t, c) for t, c in parsed
                  if forecast.created_at <= t < forecast.valid_until]
        if not window:
            continue
        as_of, first = window[0]
        previous_end = forecast.valid_until
        entry = {"symbol": forecast.symbol, "start": as_of.isoformat(),
                 "forecast_created_at": forecast.created_at.isoformat(),
                 "end_exclusive": forecast.valid_until.isoformat(),
                 "candles": len(window),
                 "terminal_valuation": "mark_to_market_not_liquidated"}
        quality = coverage_at(outcomes, symbol=forecast.symbol, horizon=horizon,
                              as_of=as_of, target=target,
                              min_samples=min_samples)
        entry["coverage_samples"] = quality.samples
        entry["coverage"] = str(quality.coverage) if quality.coverage is not None else None
        if not quality.eligible:
            entry["skipped"] = quality.reason
            results.append(entry)
            continue
        try:
            config = plan_auto(forecast, as_of=as_of, price=first["open"],
                               capital=capital, max_intervals=max_intervals,
                               **grid_options)
        except ValueError as exc:
            entry["skipped"] = "forecast_grid_unavailable: " + str(exc)
            results.append(entry)
            continue
        classic_lower = first["open"] * (1 - classic_half_width)
        classic_upper = first["open"] * (1 + classic_half_width)
        from .planner import RangeForecast
        classic_forecast = RangeForecast(forecast.symbol, forecast.created_at,
                                         forecast.valid_until,
                                         classic_lower, classic_upper)
        try:
            classic_config = plan_auto(
                classic_forecast, as_of=as_of, price=first["open"],
                capital=capital, max_intervals=max_intervals, **grid_options)
            classic_engine = GridEngine(classic_config)
        except ValueError as exc:
            classic_engine = None
            entry["classic_skipped"] = str(exc)
        forecast_engine = GridEngine(config)
        for _, candle in window:
            forecast_engine.on_candle(candle, path="low_first",
                                      allow_same_candle_reentry=False)
            if classic_engine is not None:
                classic_engine.on_candle(candle, path="low_first",
                                        allow_same_candle_reentry=False)
        entry["forecast_grid"] = forecast_engine.snapshot(include_pnl=False)
        entry["forecast_intervals"] = config.intervals
        entry["classic_grid"] = (classic_engine.snapshot(include_pnl=False)
                                  if classic_engine is not None else None)
        entry["classic_intervals"] = (classic_engine.config.intervals
                                      if classic_engine is not None else None)
        entry["buy_hold"] = buy_hold(capital, first["open"], window[-1][1]["close"],
                                     taker_fee_rate=config.taker_fee_rate,
                                     slippage=config.slippage)
        results.append(entry)
    skipped = Counter(r["skipped"].split(":")[0] for r in results if "skipped" in r)
    return {"windows": results, "total_windows": len(results),
            "traded_windows": sum("forecast_grid" in r for r in results),
            "skipped_windows": sum("skipped" in r for r in results),
            "skip_reasons": dict(skipped),
            "terminal_valuation": "mark_to_market_not_liquidated"}
