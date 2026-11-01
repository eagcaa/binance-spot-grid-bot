# Prespecified evaluation protocol (2026-11-01)

This protocol is fixed before running the new filtered-classic comparison across the 11-symbol cohort. BTCUSDT was examined beforehand to generate the hypothesis; its results must be reported separately, not included in the cohort's pass/fail totals.

## Primary exploratory test
- Horizon: **240 minutes (4 hours)**.
- Universe: **11 symbols**: ADAUSDT, AVAXUSDT, BNBUSDT, DOGEUSDT, ETHUSDT, LINKUSDT, PENDLEUSDT, PYTHUSDT, SOLUSDT, SUIUSDT, XRPUSDT. Exclude ETCUSDT (only one forecast). **BTCUSDT is the hypothesis-generating discovery sample and is excluded from the 11-symbol evaluation cohort.**
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

## Simulation correction before rerun
The initial 11-symbol run used an incorrect uniform price tick (0.01), quantity step (0.000001) and minimum notional (5 USDT), invalidating its coin-level interpretation, especially DOGEUSDT and PYTHUSDT. **Rerun the unchanged 11-symbol cohort, time range, horizon, min_samples=15 and prespecified criteria after the correction.** The corrected runner reads PRICE_FILTER.tickSize, LOT_SIZE.stepSize and NOTIONAL.minNotional (or MIN_NOTIONAL.minNotional when NOTIONAL is absent) from public Binance Spot /api/v3/exchangeInfo for each symbol, and fails closed if rules cannot be obtained. These are current exchange rules, not a historical rules snapshot; historical-rule drift remains a limitation. No orders or authenticated endpoints are used. The earlier output must not be used for final coin-level claims.

## Post-hoc diagnostic (not part of the original pass/fail criteria)
The corrected 2026-10-26 to 2026-11-01 run mechanically passed the original filter rule: classic -800.08 USDT, filtered classic -569.87 USDT, 7/11 coin wins. The forecast-band rule failed: -699.16 vs -569.87 USDT over 155 matched windows. These original results remain recorded unchanged.

An **additional, post-hoc** warm-up-separated diagnostic found the following classic-grid per-window PNL: quality accepted -3.68 USDT (155 windows), coverage rejected -2.16 USDT (65 windows), insufficient-history warm-up -0.51 USDT (176 windows). Among the seven coins having both accepted and coverage-rejected windows, accepted windows were worse in all seven. The apparent +230.21 USDT filter advantage therefore does **not** demonstrate favorable window selection; it is confounded by time out of market during warm-up and by concentration in PENDLE. This diagnostic does not retroactively change the original criterion's mechanical PASS, but **the evidence does not support deploying the filter**.

These observations were made after inspecting the initial evaluation and must not be presented as prespecified confirmation.

## Future out-of-sample evaluation (new criteria, fixed before the future period)
For a separately dated future dataset collected over approximately 3-4 weeks, use min_samples=30 and **exclude warm-up windows from the selection-quality comparison**. Evaluate classic-grid PNL on eligible/accepted versus eligible/rejected windows in the same post-warm-up period, requiring (a) higher mean classic-grid PNL for accepted windows than rejected windows, and (b) the same directional improvement in a strict majority of coins that have observations in **both** groups. Report group sizes, per-coin differences, aggregate PNL, and the buy-and-hold baseline; a missing comparison group must be reported as inconclusive, not as a win. Treat this as a new out-of-sample protocol, not a revision to the historical 7/11 decision. Do not deploy live strategies on the strength of either short sample.
