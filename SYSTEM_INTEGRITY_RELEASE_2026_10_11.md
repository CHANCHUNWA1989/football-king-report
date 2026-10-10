# 足球王者：全系統可信度與安全性更新（2026-10-11）

## Scope

This release hardens four existing research layers without modifying the V4.1
distribution archive or claiming betting profitability.

| Layer | Change | Regression tests |
| --- | --- | --- |
| Market/forecast pairing | Numeric-only probabilities, nonempty source event IDs, market-age <= 8 hours at collection, no in-play market baseline paired as prematch | `test_market_pair.py` |
| Free fixture failover | Primary provider whitelist and disabled-recommendation provenance; fallback must be a real future OpenLigaDB schedule row with distinct teams, timestamp, nonbetting flags; duplicate backup fixtures counted once | `test_free_source_failover.py` |
| Public quality gate | Malformed fixture collection or team metadata fails closed; finished/live/postponed/cancelled matches cannot enter the prematch-eligible count | `test_operations.py` |
| Bookmaker consensus | Separate PREMATCH, IN_PLAY_OR_TOO_LATE and UNKNOWN phases and reject inconsistent market-phase metadata; no production authorization | `test_market_consensus.py` |

## Validation workflow

1. Run `python -m compileall -q ops`.
2. Run `python -m unittest discover -s ops/tests -v`.
3. Inspect the GitHub Actions `Football King Regression and Failover CI` and
   `足球王者｜安全回歸測試` checks for the release commit.
4. Only merge after regression and stress checks pass.
5. Confirm the daily iPhone report workflow after merging. Treat any unfinished
   workflow as **not yet verified**.

## Data and model boundaries

- Schedule-only fallbacks are **never** executable odds.
- Market research consensus is **not** proof of independent bookmakers,
  calibrated probabilities, positive expected value, CLV or profitability.
- Historical data downloaded today cannot retroactively become a valid
  point-in-time prediction.
- Production betting recommendations remain `DISABLED`; auto-betting remains
  prohibited by the existing qualification gates.
- A passing unit suite demonstrates software behaviour against the tested
  scenarios; it is **not** an audited model hit rate.

## Outstanding evidence needed for a future recommendation release

- Authenticated, fresh executable prices and provider licence checks.
- Independently verified full-time results with immutable pre-kickoff forecasts.
- Genuine out-of-sample probability calibration, leakage checks and week-block
  stability against the market benchmark.
- Forward-settled sample thresholds, review of any remaining API quota/source
  failures and signed manual promotion. No synthetic test or untrusted JSON
  certificate can substitute for these requirements.
