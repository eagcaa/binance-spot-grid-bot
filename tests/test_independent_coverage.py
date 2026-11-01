from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from spot_grid.quality import CoverageOutcome, coverage_at

T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_large_gap_does_not_create_independent_samples():
    outcomes = [CoverageOutcome("BTCUSDT", "24h", T - timedelta(days=40),
                                True, 1440)]
    outcomes += [CoverageOutcome("BTCUSDT", "24h",
                  T - timedelta(hours=48) + timedelta(hours=i), True, 1440)
                 for i in range(47)]
    result = coverage_at(outcomes, symbol="BTCUSDT", horizon_minutes=1440,
                         as_of=T, min_samples=30)
    assert not result.eligible
    assert result.reason == "insufficient_independent_samples"
    assert result.samples == 3


def test_coverage_uses_independent_not_clustered_observations():
    outcomes = [CoverageOutcome("BTCUSDT", "1h", T - timedelta(hours=3),
                                False, 60)]
    outcomes += [CoverageOutcome("BTCUSDT", "1h",
                  T - timedelta(minutes=30) + timedelta(minutes=i),
                  True, 60) for i in range(20)]
    result = coverage_at(outcomes, symbol="BTCUSDT", horizon_minutes=60,
                         as_of=T, min_samples=2, target=D("0.7"))
    assert result.samples == 2
    assert result.coverage == D("0.5")
    assert result.reason == "coverage_below_target"


def test_future_outcomes_do_not_change_past_independent_count():
    past = [CoverageOutcome("BTCUSDT", "1h", T - timedelta(hours=i + 1),
                            True, 60) for i in range(3)]
    future = CoverageOutcome("BTCUSDT", "1h", T + timedelta(hours=1), False, 60)
    before = coverage_at(past, symbol="BTCUSDT", horizon_minutes=60,
                         as_of=T, min_samples=3)
    after = coverage_at(past + [future], symbol="BTCUSDT", horizon_minutes=60,
                        as_of=T, min_samples=3)
    assert before == after
