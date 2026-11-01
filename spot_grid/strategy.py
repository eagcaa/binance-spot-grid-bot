"""Point-in-time strategy comparison on the same full set of windows."""
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal as D

from .comparison import buy_hold
from .engine import GridEngine
from .planner import RangeForecast, plan_auto
from .quality import coverage_at


def _summary(values):
    if not values:
        return {"total_pnl": "0", "average_pnl": None,
                "win_rate": None, "worst_window_pnl": None}
    return {"total_pnl": str(sum(values, D(0))),
            "average_pnl": str(sum(values, D(0)) / len(values)),
            "win_rate": str(D(sum(v > 0 for v in values)) / len(values)),
            "worst_window_pnl": str(min(values))}


def evaluate_strategy(forecasts, candles, outcomes, *, horizon=None,
                      capital=D("1000"), target=None, coverage_tolerance=D("0.05"),
                      min_samples=30, min_history_days=0, max_intervals=50,
                      min_net_margin=D("0.0015"),
                      classic_half_width=D("0.05"), **grid_options):
    """Independent, non-compounded windows. Filter failures stay in cash.

    Classic grid resets around each window's opening price with fixed +/- width.
    All three strategies use the same windows and terminal mark-to-market basis.
    """
    if not D(0) < classic_half_width < D(1):
        raise ValueError("invalid classic_half_width")
    if not D(0) <= coverage_tolerance <= D(1):
        raise ValueError("invalid coverage_tolerance")
    parsed = []
    for candle in candles:
        stamp = datetime.fromisoformat(candle["time"].replace("Z", "+00:00"))
        if stamp.tzinfo is None or (parsed and stamp <= parsed[-1][0]):
            raise ValueError("candles must be strictly increasing and timezone-aware")
        parsed.append((stamp, candle))
    grid_options.setdefault("fill_model", "through")
    results = []
    previous_end = None
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
        # Baselines are calculated regardless of forecast eligibility.
        first_price = first["open"]
        last_price = window[-1][1]["close"]
        taker_fee = grid_options.get("taker_fee_rate", D("0.001"))
        slippage = grid_options.get("slippage", D("0.0005"))
        entry["buy_hold"] = buy_hold(capital, first_price, last_price,
                                     taker_fee_rate=taker_fee, slippage=slippage)
        classic = RangeForecast(forecast.symbol, forecast.created_at,
                                forecast.valid_until,
                                first_price * (1 - classic_half_width),
                                first_price * (1 + classic_half_width),
                                forecast.horizon_minutes, forecast.target_coverage)
        try:
            classic_config = plan_auto(
                classic, as_of=as_of, price=first_price, capital=capital,
                max_intervals=max_intervals, min_net_margin=min_net_margin,
                **grid_options)
            classic_engine = GridEngine(classic_config)
        except ValueError as exc:
            classic_engine = None
            entry["classic_skipped"] = str(exc)
        # If baseline cannot be built, cash is the explicit fallback.
        entry["classic_grid"] = None
        entry["classic_pnl"] = "0"
        entry["classic_intervals"] = None
        if classic_engine is not None:
            for _, bar in window:
                classic_engine.on_candle(bar, path="low_first",
                                         allow_same_candle_reentry=False)
            entry["classic_grid"] = classic_engine.snapshot(include_pnl=False)
            entry["classic_pnl"] = entry["classic_grid"]["pnl"]
            entry["classic_intervals"] = classic_config.intervals

        if not D(0) <= forecast.target_coverage <= D(1) or forecast.horizon_minutes <= 0:
            raise ValueError("invalid forecast horizon or target coverage")
        threshold = (max(D(0), forecast.target_coverage - coverage_tolerance)
                     if target is None else D(target))
        quality = coverage_at(outcomes, symbol=forecast.symbol, horizon=horizon,
                              horizon_minutes=forecast.horizon_minutes,
                              as_of=as_of, target=threshold,
                              min_samples=min_samples,
                              min_span=timedelta(days=min_history_days))
        entry["coverage_target"] = str(threshold)
        entry["coverage_samples"] = quality.samples
        entry["coverage"] = str(quality.coverage) if quality.coverage is not None else None
        entry["forecast_pnl"] = "0"
        entry["forecast_grid"] = None
        entry["forecast_intervals"] = None
        if not quality.eligible:
            entry["skipped"] = quality.reason
        else:
            try:
                config = plan_auto(forecast, as_of=as_of, price=first_price,
                                   capital=capital, max_intervals=max_intervals,
                                   min_net_margin=min_net_margin, **grid_options)
                forecast_engine = GridEngine(config)
            except ValueError as exc:
                entry["skipped"] = "forecast_grid_unavailable: " + str(exc)
            else:
                for _, bar in window:
                    forecast_engine.on_candle(bar, path="low_first",
                                              allow_same_candle_reentry=False)
                entry["forecast_grid"] = forecast_engine.snapshot(include_pnl=False)
                entry["forecast_pnl"] = entry["forecast_grid"]["pnl"]
                entry["forecast_intervals"] = config.intervals
        results.append(entry)
    skipped = Counter(r["skipped"].split(":")[0] for r in results if "skipped" in r)
    forecast_pnls = [D(r["forecast_pnl"]) for r in results]
    traded_pnls = [D(r["forecast_pnl"]) for r in results if r["forecast_grid"] is not None]
    classic_pnls = [D(r["classic_pnl"]) for r in results]
    hold_pnls = [D(r["buy_hold"]["pnl"]) for r in results]
    return {"windows": results, "total_windows": len(results),
            "traded_windows": sum(r["forecast_grid"] is not None for r in results),
            "skipped_windows": sum("skipped" in r for r in results),
            "skip_reasons": dict(skipped),
            "summary": {"forecast": _summary(forecast_pnls),
                        "forecast_traded_only": _summary(traded_pnls),
                        "classic": _summary(classic_pnls),
                        "buy_hold": _summary(hold_pnls),
                        "forecast_beats_classic_windows":
                            sum(a > b for a, b in zip(forecast_pnls, classic_pnls))},
            "classic_definition": "Each window re-centers at opening price +/- fixed classic_half_width; no coverage filter; invalid classic grid stays cash",
            "terminal_valuation": "mark_to_market_not_liquidated"}
