from decimal import Decimal as D

import pytest

from spot_grid.engine import GridConfig, GridEngine


@pytest.mark.parametrize("debug", [False, True])
def test_active_order_index_and_history(debug):
    engine = GridEngine(GridConfig(
        lower=D("90"), upper=D("110"), intervals=4,
        capital=D("1000"), initial_price=D("100"), debug=debug
    ))
    for _ in range(100):
        engine.on_price(D("106"))
        engine.on_price(D("99"))
        engine._assert_balances()
    assert len(engine.open_orders) == 4
    assert engine.snapshot()["open_orders"] == 4
    assert all(o["status"] == "OPEN" for o in engine.open_orders.values())
    assert len(engine.orders) > len(engine.open_orders)
    assert sum(o["status"] == "OPEN" for o in engine.orders) == 4


def test_debug_audit_raises_runtime_error_not_assert():
    engine = GridEngine(GridConfig(
        lower=D("90"), upper=D("110"), intervals=4,
        capital=D("1000"), initial_price=D("100"), debug=True
    ))
    engine.usdt_locked += D("1")
    with pytest.raises(RuntimeError, match="USDT reservation mismatch"):
        engine._assert_balances()
