from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from spot_grid.paper import PaperSession
from spot_grid.planner import RangeForecast, plan
from spot_grid.walkforward import walk_forward


T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def forecast(start=T, end=T + timedelta(hours=2)):
    return RangeForecast("BTCUSDT", start, end, D("90"), D("110"))


def candle(time, open="100", high="102", low="98", close="100"):
    return {"time": time.isoformat(), "open": D(open), "high": D(high),
            "low": D(low), "close": D(close)}


def test_planner_rejects_future_and_expired_forecasts():
    with pytest.raises(ValueError, match="future-dated"):
        plan(forecast(), as_of=T - timedelta(seconds=1), price=D("100"),
             capital=D("1000"), intervals=4)
    with pytest.raises(ValueError, match="expired"):
        plan(forecast(), as_of=T + timedelta(hours=2), price=D("100"),
             capital=D("1000"), intervals=4)


def test_walk_forward_only_uses_candles_in_validity_window():
    candles = [candle(T - timedelta(minutes=1)), candle(T),
               candle(T + timedelta(hours=1)),
               candle(T + timedelta(hours=2))]
    results = walk_forward([forecast()], candles, intervals=4)
    assert len(results) == 1
    assert results[0]["candles"] == 2
    assert results[0]["start"] == T.isoformat()


def test_walk_forward_uses_first_non_overlapping_forecast():
    candles = [candle(T), candle(T + timedelta(hours=1))]
    results = walk_forward([forecast(),
                            forecast(T + timedelta(hours=1),
                                     T + timedelta(hours=3))],
                           candles, intervals=4)
    assert len(results) == 1
    assert results[0]["forecast_created_at"] == T.isoformat()
    assert results[0]["candles"] == 2


def test_invalid_window_is_skipped_without_stopping_following_windows():
    forecasts = [forecast(T + timedelta(hours=2*i),
                          T + timedelta(hours=2*i+2)) for i in range(3)]
    candles = [candle(T, open="120", high="121", low="119", close="120"),
               candle(T + timedelta(hours=2)),
               candle(T + timedelta(hours=4))]
    results = walk_forward(forecasts, candles, intervals=4)
    assert len(results) == 3
    assert "outside forecast range" in results[0]["skipped"]
    assert all("snapshot" in result for result in results[1:])


def test_narrow_band_with_unprofitable_grids_is_skipped():
    narrow = RangeForecast("BTCUSDT", T, T + timedelta(minutes=15),
                           D("99.6"), D("100.4"))
    results = walk_forward([narrow], [candle(T)], intervals=10)
    assert len(results) == 1
    assert "skipped" in results[0]
    assert any(word in results[0]["skipped"].lower()
               for word in ("fee", "fees", "rounding", "proceeds"))


def test_paper_preserves_explicit_touch_setting():
    config = plan(forecast(), as_of=T, price=D("100"),
                  capital=D("1000"), intervals=4, fill_model="touch")
    assert PaperSession(config).engine.config.fill_model == "touch"
    assert PaperSession(config, fill_model="through").engine.config.fill_model == "through"



def test_paper_session_does_not_send_orders_and_tracks_equity():
    config = plan(forecast(), as_of=T, price=D("100"),
                  capital=D("1000"), intervals=4)
    session = PaperSession(config)
    snapshot = session.on_candle(candle(T))
    assert session.report()["events"][0]["equity"] == snapshot["equity"]
    assert session.report()["snapshot"] == snapshot
