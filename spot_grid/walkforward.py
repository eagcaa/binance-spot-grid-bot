"""Walk-forward replay: choose only forecasts known before each evaluation window."""
from datetime import datetime
from decimal import Decimal as D

from .engine import GridEngine
from .planner import plan


def walk_forward(forecasts, candles, *, capital=D("1000"), intervals=10,
                 stop_loss=None, **grid_options):
    """Non-overlapping windows; timestamps must be timezone-aware ISO strings.

    Forecast validity defines each evaluation window. Results are independent
    trials with reset capital, not a compounded portfolio equity curve.
    """
    forecasts = sorted(forecasts, key=lambda f: f.created_at)
    parsed = []
    for candle in candles:
        if "time" not in candle:
            raise ValueError("walk-forward candles require time")
        stamp = datetime.fromisoformat(candle["time"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("candle timestamps must be timezone-aware")
        if parsed and stamp <= parsed[-1][0]:
            raise ValueError("candles must be strictly increasing")
        parsed.append((stamp, candle))
    results = []
    previous_end = None
    grid_options.setdefault("fill_model", "through")
    for forecast in forecasts:
        if previous_end is not None and forecast.created_at < previous_end:
            continue
        window = [(t, c) for t, c in parsed
                  if forecast.created_at <= t < forecast.valid_until]
        if not window:
            continue
        start, first = window[0]
        try:
            config = plan(forecast, as_of=start, price=first["open"],
                          capital=capital, intervals=intervals,
                          stop_loss=stop_loss, **grid_options)
            engine = GridEngine(config)
        except ValueError as exc:
            results.append({"symbol": forecast.symbol,
                            "start": start.isoformat(), "skipped": str(exc)})
            previous_end = forecast.valid_until
            continue
        for _, candle in window:
            engine.on_candle(candle, path="low_first", allow_same_candle_reentry=False)
        results.append({"symbol": forecast.symbol,
                        "forecast_created_at": forecast.created_at.isoformat(),
                        "start": start.isoformat(),
                        "end_exclusive": forecast.valid_until.isoformat(),
                        "candles": len(window),
                        "snapshot": engine.snapshot()})
        previous_end = forecast.valid_until
    return results
