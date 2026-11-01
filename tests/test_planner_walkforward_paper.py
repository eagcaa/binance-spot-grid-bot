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


def test_walk_forward_rejects_overlapping_windows():
    candles = [candle(T), candle(T + timedelta(hours=1))]
    with pytest.raises(ValueError, match="overlapping"):
        walk_forward([forecast(),
                      forecast(T + timedelta(hours=1),
                               T + timedelta(hours=3))], candles,
                     intervals=4)


def test_paper_session_does_not_send_orders_and_tracks_equity():
    config = plan(forecast(), as_of=T, price=D("100"),
                  capital=D("1000"), intervals=4)
    session = PaperSession(config)
    snapshot = session.on_candle(candle(T))
    assert session.report()["events"][0]["equity"] == snapshot["equity"]
    assert session.report()["snapshot"] == snapshot
