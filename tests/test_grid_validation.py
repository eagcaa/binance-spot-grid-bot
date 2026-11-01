from decimal import Decimal as D

import pytest

from spot_grid.engine import GridConfig, GridEngine


def test_underfunded_grid_rejected_explicitly():
    with pytest.raises(ValueError, match="below minimum"):
        GridEngine(
            GridConfig(
                lower=D("90"),
                upper=D("110"),
                intervals=20,
                capital=D("60"),
                initial_price=D("100"),
            )
        )


def test_funded_grid_still_creates_orders():
    engine = GridEngine(
        GridConfig(
            lower=D("90"),
            upper=D("110"),
            intervals=4,
            capital=D("1000"),
            initial_price=D("100"),
        )
    )
    assert any(order["status"] == "OPEN" for order in engine.orders)

def test_replacement_order_below_minimum_rejected():
    with pytest.raises(ValueError, match="below minimum"):
        GridEngine(GridConfig(
            lower=D("90"), upper=D("110"), intervals=4,
            capital=D("20.04"), initial_price=D("100")
        ))


def test_initial_purchase_and_fee_are_recorded():
    engine = GridEngine(GridConfig(
        lower=D("90"), upper=D("110"), intervals=4,
        capital=D("1000"), initial_price=D("100")
    ))
    assert engine.initial_trades
    for trade in engine.initial_trades:
        assert trade["fee_asset"] == "ASSET"
        assert trade["net_qty"] == trade["gross_qty"] - trade["fee"]
        assert trade["cost_usdt"] == trade["gross_qty"] * trade["price"]
    assert D(engine.snapshot()["equity"]) < D("1000")


def test_replacement_cycle_at_100():
    engine = GridEngine(GridConfig(
        lower=D("90"), upper=D("110"), intervals=4,
        capital=D("1000"), initial_price=D("100")
    ))
    engine.on_price(D("106"))
    engine.on_price(D("99"))
    assert any(fill["side"] == "BUY" and fill["price"] == D("100")
               for fill in engine.fills)


def test_invalid_order_does_not_silently_disappear():
    engine = GridEngine(GridConfig(
        lower=D("90"), upper=D("110"), intervals=4,
        capital=D("1000"), initial_price=D("100")
    ))
    with pytest.raises(RuntimeError, match="below minimum"):
        engine._order("BUY", D("100"), D("0.01"))


def test_fixed_buy_quantity_after_200_cycles():
    engine = GridEngine(GridConfig(
        lower=D("90"), upper=D("110"), intervals=4,
        capital=D("22"), initial_price=D("100")
    ))
    expected = engine.buy_qty[2]
    for _ in range(200):
        engine.on_price(D("106"))
        engine.on_price(D("99"))
    buys = [fill for fill in engine.fills
            if fill["side"] == "BUY" and fill["price"] == D("100")]
    assert len(buys) == 200
    assert all(fill["qty"] == expected for fill in buys)
    assert any(order["status"] == "OPEN" and order["side"] == "BUY"
               and order["price"] == D("100") and order["qty"] == expected
               for order in engine.orders)
