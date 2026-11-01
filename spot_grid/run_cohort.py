"""Run the prespecified 11-symbol, four-hour evaluation (read-only).

Usage:
    python -m spot_grid.run_cohort

BTC is a discovery sample, not part of the cohort.
"""
import contextlib
import io
from decimal import Decimal as D

from .run_market import main as run_one

SYMBOLS = (
    "ADAUSDT", "AVAXUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "LINKUSDT", "PENDLEUSDT", "PYTHUSDT", "SOLUSDT", "SUIUSDT",
    "XRPUSDT",
)
START = "2026-10-26T00:00:00+00:00"
END = "2026-11-01T00:00:00+00:00"
HORIZON_MINUTES = 240
MIN_SAMPLES = 15


def aggregate(reports):
    """Compute fixed criteria without altering missing/failed symbol results."""
    if set(reports) != set(SYMBOLS):
        raise ValueError("all 11 prespecified symbols must be present")
    total_classic = D(0)
    total_filtered = D(0)
    matched_forecast = D(0)
    matched_filtered = D(0)
    matched_windows = 0
    wins = 0
    rows = []
    for symbol in SYMBOLS:
        report = reports[symbol]
        summary = report["summary"]
        classic = D(summary["classic"]["total_pnl"])
        filtered = D(summary["filtered_classic"]["total_pnl"])
        matched = summary["forecast_vs_filtered_same_windows"]
        forecast_same = D(matched["forecast_total_pnl"])
        filtered_same = D(matched["filtered_classic_total_pnl"])
        n = int(matched["windows"])
        total_classic += classic
        total_filtered += filtered
        matched_forecast += forecast_same
        matched_filtered += filtered_same
        matched_windows += n
        wins += filtered > classic
        rows.append({
            "symbol": symbol, "classic": classic, "filtered_classic": filtered,
            "forecast_matched": forecast_same, "filtered_matched": filtered_same,
            "matched_windows": n, "filter_win": filtered > classic,
            "total_windows": report["total_windows"],
            "forecast_traded": report["traded_windows"],
            "filtered_traded": sum(
                w["filtered_classic_grid"] is not None for w in report["windows"]
            ),
        })
    return {
        "rows": rows, "classic_total": total_classic,
        "filtered_classic_total": total_filtered,
        "filter_winning_symbols": wins,
        "filter_pass": total_filtered > total_classic and wins >= 7,
        "matched_windows": matched_windows,
        "forecast_matched_total": matched_forecast,
        "filtered_classic_matched_total": matched_filtered,
        "band_pass": matched_windows > 0 and matched_forecast > matched_filtered,
    }


def main():
    reports = {}
    for symbol in SYMBOLS:
        args = [
            "--symbol", symbol, "--start", START, "--end", END,
            "--horizon-minutes", str(HORIZON_MINUTES),
            "--min-samples", str(MIN_SAMPLES),
        ]
        print(f"Evaluating {symbol}...", flush=True)
        # Suppress verbose per-symbol CLI; retain complete in-memory reports.
        with contextlib.redirect_stdout(io.StringIO()):
            reports[symbol] = run_one(args)
    result = aggregate(reports)
    print("\nPRE-REGISTERED 11-SYMBOL COHORT (BTC excluded)")
    print("Symbol       Windows ForecastTraded FilteredTraded Classic     Filtered    Matched  ForecastSame FilteredSame")
    for row in result["rows"]:
        print(f"{row['symbol']:<12} {row['total_windows']:>7} "
              f"{row['forecast_traded']:>14} {row['filtered_traded']:>13} "
              f"{row['classic']:>10.2f} {row['filtered_classic']:>11.2f} "
              f"{row['matched_windows']:>7} {row['forecast_matched']:>12.2f} "
              f"{row['filtered_matched']:>12.2f}")
    print(f"\nFILTER: classic={result['classic_total']:.2f} "
          f"filtered={result['filtered_classic_total']:.2f}; "
          f"coin wins={result['filter_winning_symbols']}/11 "
          f"(required >=7); PASS={result['filter_pass']}")
    print(f"BAND: matched windows={result['matched_windows']}; "
          f"forecast={result['forecast_matched_total']:.2f}; "
          f"filtered classic={result['filtered_classic_matched_total']:.2f}; "
          f"PASS={result['band_pass']}")
    print("Interpretation: short, correlated exploratory sample; not live-trading validation.")
    return result


if __name__ == "__main__":
    main()
