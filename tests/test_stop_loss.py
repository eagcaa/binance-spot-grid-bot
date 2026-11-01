from decimal import Decimal as D

import pytest

from spot_grid.engine import GridConfig, GridEngine


def engine(**overrides):
    values = dict(lower=D("90"), upper=D("110"), intervals=4,
                  capital=D("1000"), initial_price=D("100"),
                  stop_loss=D("85"))
    values.update(overrides)
    return GridEngine(GridConfig(**values))


def candle(o, h, l, c):
    return {"open": D(o), "high": D(h), "low": D(l), "close": D(c)}


@pytest.mark.parametrize("stop", ["90", "91", "0", "-1"])
def test_stop_must_be_below_lower_bound(stop):
    with pytest.raises(ValueError, match="stop_loss"):
        engine(stop_loss=D(stop))


def test_stop_touch_liquidates_before_grid_fills():
    e = engine(slippage=D("0"))
    e.on_candle(candle("100", "110", "85", "100"))
    assert e.stopped
    assert e.stop_trades[0]["price"] == D("85")
    assert [f["price"] for f in e.fills] == [D("95"), D("90")]
    assert e.usdt_locked == e.asset_locked == 0
    assert len(e.open_orders) == 0
    assert all(o["status"] in ("FILLED", "CANCELLED") for o in e.orders)
    assert {o["price"] for o in e.orders if o["status"] == "FILLED"} == {D("95"), D("90")}
    previous = e.snapshot()
    e.on_candle(candle("100", "110", "80", "100"))
    e.on_price(D("95"))
    assert e.snapshot() == previous


def test_gap_open_uses_open_price_and_applies_taker_cost():
    e = engine(taker_fee_rate=D("0.002"), slippage=D("0.01"))
    e.on_candle(candle("80", "100", "75", "90"))
    trade = e.stop_trades[0]
    assert trade["trigger_price"] == D("80")
    assert trade["price"] == D("79.20")
    assert trade["fee"] == trade["qty"] * D("79.20") * D("0.002")
    assert e.asset_free < e.config.qty_step
    assert e.snapshot()["dust_asset"] == str(e.asset_free)


def test_outside_band_counts_candles_and_excursions():
    e = engine(stop_loss=None)
    for c in [
        candle("100", "112", "99", "111"),
        candle("111", "113", "100", "112"),
        candle("105", "108", "95", "100"),
        candle("100", "102", "89", "90"),
    ]:
        e.on_candle(c)
    assert e.outside_candles == 3
    assert e.outside_entries == 2


def test_stop_candle_fills_downward_buys_before_liquidation():
    e = engine(slippage=D("0"))
    e.on_candle(candle("100", "100", "84", "84"))
    assert [f["price"] for f in e.fills] == [D("95"), D("90")]
    assert D("9") < e.stop_trades[0]["qty"] < D("11")
    assert e.stop_trades[0]["trigger_price"] == D("85")
    assert e.stopped


def test_price_stream_stop_fills_crossed_buys():
    e = engine(slippage=D("0"))
    e.on_price(D("84"))
    assert [f["price"] for f in e.fills] == [D("95"), D("90")]
    assert e.stop_trades[0]["trigger_price"] == D("84")
    assert e.stopped


def test_stop_candle_ignores_profitable_sell_even_if_high_touched():
    e = engine(slippage=D("0"))
    e.on_candle(candle("100", "110", "84", "100"))
    assert all(f["side"] == "BUY" for f in e.fills)
