"""Read-only forecast planning. No DB writes or exchange calls."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal as D

from .engine import GridConfig


@dataclass(frozen=True)
class RangeForecast:
    symbol: str
    created_at: datetime
    valid_until: datetime
    lower: D
    upper: D


def plan(forecast: RangeForecast, *, as_of: datetime, price: D,
         capital: D, intervals: int = 10, stop_loss: D | None = None,
         **grid_options) -> GridConfig:
    """Only use a forecast already published and still valid at as_of."""
    if forecast.created_at.tzinfo is None or forecast.valid_until.tzinfo is None or as_of.tzinfo is None:
        raise ValueError("forecast timestamps must be timezone-aware")
    if not (forecast.created_at <= as_of < forecast.valid_until):
        raise ValueError("forecast is future-dated or expired")
    if not (forecast.lower <= price <= forecast.upper):
        raise ValueError("price outside forecast range; skip this window")
    if stop_loss is not None and stop_loss >= forecast.lower:
        raise ValueError("stop must be below forecast lower bound")
    return GridConfig(lower=forecast.lower, upper=forecast.upper,
                      intervals=intervals, capital=capital,
                      initial_price=price, stop_loss=stop_loss, **grid_options)


def plan_auto(forecast: RangeForecast, *, as_of: datetime, price: D,
              capital: D, max_intervals: int = 50, min_intervals: int = 2,
              stop_loss: D | None = None, **grid_options) -> GridConfig:
    """Choose the largest interval count passing real engine validations."""
    from .engine import GridEngine

    if min_intervals < 2 or max_intervals < min_intervals:
        raise ValueError("invalid grid interval search limits")
    last_error = None
    for intervals in range(max_intervals, min_intervals - 1, -1):
        try:
            config = plan(forecast, as_of=as_of, price=price,
                          capital=capital, intervals=intervals,
                          stop_loss=stop_loss, **grid_options)
            GridEngine(config)
            return config
        except ValueError as exc:
            last_error = exc
    raise ValueError(f"no viable grid count: {last_error}")
