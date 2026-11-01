from decimal import Decimal as D

import pytest

from spot_grid.engine import GridConfig, GridEngine


def engine(**overrides):
    values = dict(lower=D("90"), upper=D("110"), intervals=4,
                  capital=D("1000"), initial_price=D("100"))
    values.update(overrides)
    return GridEngine(GridConfig(**values))


def assert_reconciles(e):
    snapshot = e.snapshot()
    pnl = snapshot["pnl_breakdown"]
    assert abs(D(pnl["pnl_reconciled_usdt"]) - D(snapshot["pnl"])) < D("0.00000001")
    assert D(pnl["dust_asset"]) < e.config.qty_step


def test_initial_inventory_cost_basis_reconciles():
    e = engine()
    assert_reconciles(e)
    assert D(e.snapshot()["pnl_breakdown"]["initial_maker_fees_asset"]) > 0


def test_grid_roundtrip_reconciles():
    e = engine()
    e.on_price(D("94"))
    e.on_price(D("106"))
    assert_reconciles(e)
    p = e.snapshot()["pnl_breakdown"]
    assert D(p["maker_fees_usdt"]) > 0
    assert D(p["grid_realized_gross_usdt"]) != 0


def test_stop_with_gap_reconciles_and_reports_dust():
    e = engine(stop_loss=D("85"))
    e.on_candle({"open": D("80"), "high": D("90"),
                 "low": D("75"), "close": D("82")})
    assert e.stopped
    assert_reconciles(e)
    p = e.snapshot()["pnl_breakdown"]
    assert D(p["taker_fees_usdt"]) > 0
    assert D(p["stop_realized_gross_usdt"]) < 0


@pytest.mark.parametrize("prices", [
    ["94", "99", "106", "94", "101"],
    ["110", "90", "110", "90"],
    ["99", "98", "97", "96"],
])
def test_multiple_price_paths_reconcile(prices):
    e = engine()
    for price in prices:
        e.on_price(D(price))
        assert_reconciles(e)


def test_start_marketable_sell_precedes_newly_reached_buy():
    e = engine()
    # Create a SELL that is already marketable at the segment start,
    # then move down across an outstanding BUY.
    e.on_price(D("106"))
    e.last_price = D("106")
    # Assert stable accounting under the mixed-side segment.
    e.on_price(D("94"))
    assert_reconciles(e)
