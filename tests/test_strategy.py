from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from spot_grid.planner import RangeForecast, plan_auto
from spot_grid.quality import CoverageOutcome, coverage_at
from spot_grid.strategy import evaluate_strategy


T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def forecast(start=T):
    return RangeForecast("BTCUSDT", start, start + timedelta(hours=1),
                         D("90"), D("110"))


def candle(at):
    return {"time": at.isoformat(), "open": D("100"), "high": D("102"),
            "low": D("98"), "close": D("100")}


def test_future_and_equal_time_outcomes_are_excluded():
    outcomes = [
        CoverageOutcome("BTCUSDT", "1h", T - timedelta(seconds=1), True),
        CoverageOutcome("BTCUSDT", "1h", T, False),
        CoverageOutcome("BTCUSDT", "1h", T + timedelta(seconds=1), False),
        CoverageOutcome("ETHUSDT", "1h", T - timedelta(seconds=1), False),
        CoverageOutcome("BTCUSDT", "4h", T - timedelta(seconds=1), False),
    ]
    result = coverage_at(outcomes, symbol="BTCUSDT", horizon="1h",
                         as_of=T, min_samples=1)
    assert result.eligible
    assert result.samples == 1
    assert result.coverage == D(1)


def test_insufficient_and_low_coverage_are_distinct():
    outcomes = [CoverageOutcome("BTCUSDT", "1h", T - timedelta(minutes=i+1),
                                i == 0) for i in range(3)]
    assert coverage_at(outcomes, symbol="BTCUSDT", horizon="1h",
                       as_of=T, min_samples=4).reason == "insufficient_history"
    assert coverage_at(outcomes, symbol="BTCUSDT", horizon="1h",
                       as_of=T, min_samples=3).reason == "coverage_below_target"


def test_auto_grid_is_largest_feasible_count():
    config = plan_auto(forecast(), as_of=T, price=D("100"),
                       capital=D("1000"), max_intervals=12)
    assert 2 <= config.intervals <= 12
    from spot_grid.engine import GridEngine
    GridEngine(config)
    for count in range(config.intervals + 1, 13):
        from spot_grid.planner import plan
        import pytest
        with pytest.raises(ValueError):
            GridEngine(plan(forecast(), as_of=T, price=D("100"),
                            capital=D("1000"), intervals=count))


def test_strategy_excludes_future_evaluations_and_compares_same_window():
    later = T + timedelta(hours=1)
    forecasts = [forecast(T), forecast(later)]
    candles = [candle(T), candle(later)]
    outcomes = [CoverageOutcome("BTCUSDT", "1h", T - timedelta(seconds=1), True),
                CoverageOutcome("BTCUSDT", "1h", later + timedelta(seconds=1), False)]
    report = evaluate_strategy(forecasts, candles, outcomes, horizon="1h",
                               min_samples=1, max_intervals=6)
    assert report["total_windows"] == 2
    assert report["traded_windows"] == 2
    assert report["skipped_windows"] == 0
    assert all(r["forecast_grid"] and r["classic_grid"] and r["buy_hold"]
               for r in report["windows"])
    assert all(r["coverage"] == "1" for r in report["windows"])
    assert report["terminal_valuation"] == "mark_to_market_not_liquidated"


def test_strategy_skips_when_coverage_unknown():
    report = evaluate_strategy([forecast()], [candle(T)], [],
                               horizon="1h", min_samples=1)
    assert report["traded_windows"] == 0
    assert report["skip_reasons"] == {"insufficient_history": 1}
