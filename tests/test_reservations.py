from decimal import Decimal as D

import pytest

from spot_grid.engine import GridConfig, GridEngine


def make(capital="1000"):
    return GridEngine(GridConfig(
        lower=D("90"), upper=D("110"), intervals=4,
        capital=D(capital), initial_price=D("100")
    ))


def check_reservations(engine):
    buys = sum((o["price"] * o["qty"] for o in engine.orders
                if o["status"] == "OPEN" and o["side"] == "BUY"), D(0))
    sells = sum((o["qty"] for o in engine.orders
                 if o["status"] == "OPEN" and o["side"] == "SELL"), D(0))
    assert engine.usdt_locked == buys
    assert engine.asset_locked == sells
    assert engine.usdt == engine.usdt_free + engine.usdt_locked
    assert engine.asset == engine.asset_free + engine.asset_locked
    assert min(engine.usdt_free, engine.usdt_locked,
               engine.asset_free, engine.asset_locked) >= 0


def test_initial_orders_are_fully_reserved():
    engine = make()
    check_reservations(engine)
    assert engine.usdt_locked > 0
    assert engine.asset_locked > 0


def test_balances_remain_reserved_after_fills():
    engine = make()
    for price in ["106", "99", "94", "106", "99"]:
        engine.on_price(D(price))
        check_reservations(engine)


def test_no_double_spend_on_order_creation():
    engine = make()
    with pytest.raises(RuntimeError, match="insufficient free USDT"):
        engine._order("BUY", D("100"), D("100"))
    check_reservations(engine)
    with pytest.raises(RuntimeError, match="insufficient free asset"):
        engine._order("SELL", D("105"), D("100"))
    check_reservations(engine)


def test_200_cycles_with_small_capital():
    engine = make("22")
    original = engine.buy_qty[2]
    for _ in range(200):
        engine.on_price(D("106"))
        check_reservations(engine)
        engine.on_price(D("99"))
        check_reservations(engine)
    buys = [f for f in engine.fills
            if f["side"] == "BUY" and f["price"] == D("100")]
    assert len(buys) == 200
    assert all(f["qty"] == original for f in buys)


@pytest.mark.parametrize("capital", ["30", "1000"])
def test_narrow_grid_rejected_before_first_trade(capital):
    with pytest.raises(ValueError, match="fees and quantity rounding"):
        GridEngine(GridConfig(
            lower=D("99.80"), upper=D("100.20"), intervals=4,
            capital=D(capital), initial_price=D("100")
        ))


def test_wide_grid_passes_fee_spacing_guard():
    engine = make("1000")
    assert engine.levels[1] > engine.levels[0]


@pytest.mark.parametrize("capital", ["200", "1000"])
def test_btc_sized_step_rounding_rejected(capital):
    with pytest.raises(ValueError, match="fees and quantity rounding"):
        GridEngine(GridConfig(
            lower=D("95000"), upper=D("105000"), intervals=10,
            capital=D(capital), initial_price=D("100000"),
            qty_step=D("0.00001"), tick=D("0.01"),
        ))


def test_startup_funding_is_within_capital():
    engine = make("1000")
    initial_cost = sum((t["cost_usdt"] for t in engine.initial_trades), D(0))
    assert initial_cost + engine.usdt_locked <= D("1000")
    assert engine.usdt_free >= 0
