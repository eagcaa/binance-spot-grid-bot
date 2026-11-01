from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from spot_grid.forecast_reader import decode_rows
from spot_grid.quality import coverage_at


T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_reader_maps_real_schema_and_excludes_pending_outcomes():
    rows = [
        ("BTCUSDT", T, T + timedelta(hours=24), 1440, D("0.70"),
         D("90"), D("110"), "evaluated", True, T + timedelta(hours=25)),
        ("BTCUSDT", T + timedelta(hours=1), T + timedelta(hours=25),
         1440, D("0.70"), D("91"), D("111"), "pending", None, None),
    ]
    forecasts, outcomes = decode_rows(rows)
    assert len(forecasts) == 2
    assert forecasts[0].horizon_minutes == 1440
    assert forecasts[0].target_coverage == D("0.70")
    assert len(outcomes) == 1
    assert outcomes[0].horizon_minutes == 1440
    assert coverage_at(outcomes, symbol="BTCUSDT", horizon_minutes=1440,
                       as_of=T + timedelta(hours=24), min_samples=1).samples == 0
    assert coverage_at(outcomes, symbol="BTCUSDT", horizon_minutes=1440,
                       as_of=T + timedelta(hours=26), min_samples=1).samples == 1
