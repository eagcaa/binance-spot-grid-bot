"""Comparable terminal mark-to-market results for a single forecast window."""
from dataclasses import replace
from decimal import Decimal as D

from .engine import GridEngine


def buy_hold(capital, first_price, final_price, *,
             taker_fee_rate=D("0.001"), slippage=D("0.0005")):
    """Buy at start and mark remaining base asset at final price (not liquidated)."""
    if min(capital, first_price, final_price) <= 0:
        raise ValueError("positive capital and prices required")
    if not (D(0) <= taker_fee_rate < 1 and D(0) <= slippage < 1):
        raise ValueError("invalid fees or slippage")
    acquired = capital / (first_price * (1 + slippage))
    net = acquired * (1 - taker_fee_rate)
    equity = net * final_price
    return {"equity": str(equity), "pnl": str(equity - capital),
            "terminal_valuation": "mark_to_market_not_liquidated"}


def compare_window(forecast_config, candles, *, classic_lower, classic_upper):
    """Use the same candles, capital and fill rules for forecast/classic grids."""
    if not candles:
        raise ValueError("empty comparison window")
    forecast_engine = GridEngine(forecast_config)
    classic_config = replace(forecast_config, lower=D(str(classic_lower)),
                             upper=D(str(classic_upper)))
    classic_engine = GridEngine(classic_config)
    for candle in candles:
        forecast_engine.on_candle(candle, path="low_first",
                                  allow_same_candle_reentry=False)
        classic_engine.on_candle(candle, path="low_first",
                                 allow_same_candle_reentry=False)
    return {
        "forecast_grid": forecast_engine.snapshot(),
        "classic_grid": classic_engine.snapshot(),
        "buy_hold": buy_hold(forecast_config.capital,
                             candles[0]["open"], candles[-1]["close"],
                             taker_fee_rate=forecast_config.taker_fee_rate,
                             slippage=forecast_config.slippage),
        "terminal_valuation": "mark_to_market_not_liquidated",
    }
