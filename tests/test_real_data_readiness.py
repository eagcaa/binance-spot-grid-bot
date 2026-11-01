from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from spot_grid.planner import RangeForecast
from spot_grid.quality import CoverageOutcome, coverage_at
from spot_grid.strategy import evaluate_strategy


T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_forecast_requires_explicit_horizon_and_target():
    with pytest.raises(TypeError):
        RangeForecast("BTCUSDT", T, T + timedelta(hours=1), D("90"), D("110"))


def test_coverage_requires_independent_time_span_when_requested():
    outcomes = [CoverageOutcome("BTCUSDT", "24h",
                T - timedelta(days=i + 1), True, 1440) for i in range(30)]
    blocked = coverage_at(outcomes, symbol="BTCUSDT", horizon_minutes=1440,
                          as_of=T, min_samples=30, min_span=timedelta(days=40))
    assert blocked.reason == "insufficient_time_span"
    assert blocked.samples == 30
    allowed = coverage_at(outcomes, symbol="BTCUSDT", horizon_minutes=1440,
                          as_of=T, min_samples=30)
    assert allowed.eligible


def test_traded_only_win_rate_excludes_cash_windows():
    forecast = RangeForecast("BTCUSDT", T, T + timedelta(hours=1),
                             D("90"), D("110"), 60, D("0.70"))
    candle = {"time": T.isoformat(), "open": D("100"),
              "high": D("100"), "low": D("100"), "close": D("100")}
    report = evaluate_strategy([forecast], [candle], [], min_samples=1)
    assert report["summary"]["forecast"]["win_rate"] == "0"
    assert report["summary"]["forecast_traded_only"]["win_rate"] is None
