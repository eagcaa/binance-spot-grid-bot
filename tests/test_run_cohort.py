from decimal import Decimal as D

import pytest

from spot_grid.run_cohort import SYMBOLS, aggregate


def make_report(classic, filtered, forecast_same, filtered_same, n=2):
    return {
        "summary": {
            "classic": {"total_pnl": str(classic)},
            "filtered_classic": {"total_pnl": str(filtered)},
            "forecast_vs_filtered_same_windows": {
                "windows": n,
                "forecast_total_pnl": str(forecast_same),
                "filtered_classic_total_pnl": str(filtered_same),
            },
        },
        "total_windows": 3,
        "traded_windows": n,
        "windows": [
            {"filtered_classic_grid": {"pnl": str(filtered)}} for _ in range(n)
        ] + [{"filtered_classic_grid": None}],
    }


def test_cohort_requires_exact_prespecified_symbols():
    reports = {s: make_report(-2, -1, -1, -2) for s in SYMBOLS}
    reports.pop("SUIUSDT")
    with pytest.raises(ValueError, match="all 11"):
        aggregate(reports)
    reports["SUIUSDT"] = make_report(-2, -1, -1, -2)
    reports["BTCUSDT"] = make_report(-2, -1, -1, -2)
    with pytest.raises(ValueError, match="all 11"):
        aggregate(reports)


def test_filter_requires_total_win_and_seven_symbol_wins():
    reports = {}
    for i, symbol in enumerate(SYMBOLS):
        reports[symbol] = make_report(-10, -9 if i < 7 else -11, -2, -1)
    result = aggregate(reports)
    assert result["filter_winning_symbols"] == 7
    assert result["filter_pass"]
    assert result["classic_total"] == D("-110")
    assert result["filtered_classic_total"] == D("-107")
    assert result["matched_windows"] == 22
    assert not result["band_pass"]
    reports[SYMBOLS[6]] = make_report(-10, -11, -2, -1)
    assert not aggregate(reports)["filter_pass"]


def test_band_uses_only_matched_windows_and_requires_trades():
    reports = {s: make_report(-10, -9, 2, 1) for s in SYMBOLS}
    assert aggregate(reports)["band_pass"]
    reports = {s: make_report(-10, -9, 0, 0, n=0) for s in SYMBOLS}
    assert not aggregate(reports)["band_pass"]
