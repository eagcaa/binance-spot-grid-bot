from decimal import Decimal as D

import pytest

from spot_grid.engine import GridConfig
from spot_grid.ohlc import compare_paths, read_ohlc, replay_ohlc


def config():
    return GridConfig(lower=D("90"), upper=D("110"), intervals=4,
                      capital=D("1000"), initial_price=D("100"))


def test_paths_produce_separate_snapshots():
    candles = [{"open": D("100"), "high": D("106"),
                "low": D("94"), "close": D("100")}]
    results = compare_paths(config(), candles)
    assert set(results) == {"high_first_optimistic_touch", "low_first_optimistic_touch",
                            "high_first_conservative_through", "low_first_conservative_through"}
    assert all(D(result["equity"]) > 0 for result in results.values())


def test_reject_invalid_path():
    with pytest.raises(ValueError, match="path"):
        replay_ohlc(config(), [], "unknown")


def test_ohlc_csv_validation(tmp_path):
    csv_file = tmp_path / "candles.csv"
    csv_file.write_text("open,high,low,close\\n100,101,99,100\\n".replace("\\n", "\n"))
    assert len(read_ohlc(csv_file)) == 1
    csv_file.write_text("open,high,low,close\\n100,99,98,100\\n".replace("\\n", "\n"))
    with pytest.raises(ValueError, match="inconsistent"):
        read_ohlc(csv_file)


def test_no_non_finite_prices(tmp_path):
    csv_file = tmp_path / "candles.csv"
    csv_file.write_text("open,high,low,close\\n100,NaN,99,100\\n".replace("\\n", "\n"))
    with pytest.raises(ValueError, match="non-positive or non-finite"):
        read_ohlc(csv_file)


def test_candle_new_opposite_order_not_eligible_until_next_candle():
    candle = {"open": D("100"), "high": D("106"),
              "low": D("94"), "close": D("100")}
    optimistic = replay_ohlc(config(), [candle], "low_first", conservative=False)
    conservative = replay_ohlc(config(), [candle], "low_first", conservative=True)
    assert len(optimistic.fills) > len(conservative.fills)
    assert all(fill["order_id"] <= 4 for fill in conservative.fills)


def test_through_requires_price_beyond_level():
    from dataclasses import replace
    engine = replay_ohlc(replace(config(), fill_model="through",
                                 through_bps=D("5")),
                         [{"open": D("100"), "high": D("100"),
                           "low": D("95"), "close": D("100")}])
    assert not engine.fills


def test_reject_duplicate_or_reversed_timestamps(tmp_path):
    path = tmp_path / "candles.csv"
    path.write_text("open_time,open,high,low,close\\n"
                    "1700000000000,100,101,99,100\\n"
                    "1700000000000,100,101,99,100\\n".replace("\\n", "\n"))
    with pytest.raises(ValueError, match="strictly increase"):
        read_ohlc(path)
