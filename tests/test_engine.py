from decimal import Decimal as D
import pytest
from spot_grid.engine import GridConfig, GridEngine

def make(**kwargs):
    values=dict(lower=D("90"),upper=D("110"),intervals=4,
                capital=D("1000"),initial_price=D("100"))
    values.update(kwargs)
    return GridEngine(GridConfig(**values))

def test_levels():
    assert make().levels==list(map(D,["90","95","100","105","110"]))

def test_buy_sell():
    e=make()
    e.on_price(D("94"))
    assert any(f["side"]=="BUY" for f in e.fills)
    e.on_price(D("102"))
    assert any(f["side"]=="SELL" for f in e.fills)
    assert D(e.snapshot()["fees_usdt"])>0

def test_no_change():
    e=make()
    e.on_price(D("100"))
    assert not e.fills

def test_geometric():
    e=make(mode="geometric")
    assert len(e.levels)==5
    assert e.levels==sorted(e.levels)

def test_bad_range():
    with pytest.raises(ValueError):
        make(lower=D("120"))
