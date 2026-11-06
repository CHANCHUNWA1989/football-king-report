# Historical forecast inventory — evidence audit (2026-11-06)

Issue #452 · Draft PR #451 · Research-only / HOLD

## What was actually checked
- Latest branch commit at audit start: `8b4a41a6d32c5432f87244419c36fdfef589159d`.
- Research settlement/backtest CI, offline 1X2 validation, unified prediction ledger CI, and repository safety CI were green at audit time. Full regression and Chinese-language safety workflow were still running.
- Searched GitHub default-branch code index for: `prediction ledger`, `forecast_created_at`, `model_version`, `predictions`, `odds_snapshot`. **No results were returned by the code-search interface.** This is NOT evidence that such data/files do not exist.
- Directly attempted three likely paths: `.github/workflows/unified-prediction-ledger-tests.yml`, `ops/prediction_ledger.py`, `ops/unified_prediction_ledger.py`; all returned not found. These guesses are NOT an exhaustive repository inventory.
- Reviewed research branch `ops/frozen_forecast_join.py`, `ops/bookmaker_timestamp_gate.py`, `ops/the_odds_api_adapter.py`. These modules validate structure and time ordering; they do not fetch a historical dataset or independently attest forecast creation.

## Evidence still missing
1. Exact repository path / artifact location for immutable historical forecast ledger (if one exists).
2. Original recorded event IDs, model versions, model hashes, training cutoffs, forecast creation timestamps and score probability distributions.
3. Provenance demonstrating forecasts were stored *before* the quoted odds and kickoff, and were not reconstructed after outcomes.
4. Licensed bookmaker history with per-quote capture timestamps and independently verified outcomes.
5. Immutable dataset hashes, chronological holdout and independent review.

## Next executable action once a real source is identified
- Inspect a small authorized, redacted sample from the real ledger; check schema and timestamps.
- Join only with independently timestamped odds snapshots using the raw-envelope entry point.
- Produce coverage and exclusion counts *before* ROI/EV calculations.
- If there are no archived pre-match forecasts, start a prospective shadow ledger now; **do not** call retrospective reconstructed forecasts out-of-sample.

## Decision
**BLOCKED ON REAL EVIDENCE; PRODUCTION_RECOMMENDATIONS=DISABLED.** Passing synthetic tests does not validate real-world profitability. Do not merge/deploy or claim positive EV.
