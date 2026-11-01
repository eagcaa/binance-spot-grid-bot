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
