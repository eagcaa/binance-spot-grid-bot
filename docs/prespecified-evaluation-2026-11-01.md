# Prespecified evaluation protocol (2026-11-01)

This protocol is fixed before running the new filtered-classic comparison across coins.

## Primary exploratory test
- Horizon: **240 minutes (4 hours)**.
- Universe: **11 symbols**: ADAUSDT, AVAXUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, LINKUSDT, PENDLEUSDT, PYTHUSDT, SOLUSDT, XRPUSDT. Exclude ETCUSDT (only one forecast); exclude SUIUSDT from this initial fixed 11-symbol cohort.
- Shared UTC interval: **2026-10-26T00:00:00+00:00 through 2026-11-01T00:00:00+00:00** (end exclusive).
- Capital: 1000 USDT per independent window; min_samples: 15 for this short exploratory dataset, and default min_samples: 30 for later confirmatory runs. No compounding.
- Baseline classic grid: +/- 5% of each window opening price, unchanged fees, slippage, fill model and candle interval.
- Filtered classic: same classic grid only if historical coverage eligibility passes at that window's as-of time. Forecast grid construction failure does not block filtered classic.
- Forecast grid: original forecast band, subject to the same quality filter and grid feasibility rules.
- Buy-and-hold: unchanged, on the same windows.

## Decisions specified before inspecting cross-symbol results
1. **Filter criterion**: filtered classic total PNL across all 11 symbols exceeds unfiltered classic total PNL, **and** filtered classic exceeds classic in at least **7 of 11 symbols**.
2. **Band criterion**: forecast-grid total PNL exceeds filtered-classic PNL **on exactly the matched windows where forecast-grid actually traded**. Do not compare unmatched overall totals to judge the band.
3. Report the number of eligible, forecast-traded, and filtered-classic-traded windows; each coin's PNL and decision; gross grid PNL, gross stop PNL, unrealized inventory PNL, and quote-denominated fees. Asset-denominated fees are already included in cost basis, so do not subtract them again.
4. One-hour horizon is secondary/exploratory. Fifteen-minute horizon is excluded from the primary evaluation because forecast bands often cannot support a viable grid.
5. Correlated symbols and overlapping market regimes mean 11 symbols are **not 11 independent replications**. The seven-day sample is hypothesis-generating only; do not call it validated or live-trading ready.

**Do not modify the upstream forecast generator as part of this experiment.**
