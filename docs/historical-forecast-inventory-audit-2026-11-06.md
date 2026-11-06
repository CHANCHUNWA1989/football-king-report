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


## Follow-up correction: existing prospective pipeline found
A subsequent direct read of default-branch `README.md`, `ops/market_pair.py`, and `ops/forward_validation.py` established that the repository **already contains** a forward-only shadow forecasting and archived pairing pipeline. The README documents `shadow/`, `history/`, `market/history/`, and `research_pairs/` as intended archive paths; `ops/forward_validation.py` reads gzipped archived comparisons and applies chronology checks. `ops/market_pair.py` pairs 1X2 model probability vectors against earlier de-vigged 1X2 market baselines. The previous failed search for exact field names was insufficient to locate these existing modules; do not interpret it as absence of a ledger.

**Crucial compatibility gap:** this existing 1X2 pipeline stores derived market probabilities rather than raw executable bookmaker prices, and its documented chronology is market snapshot <= forecast <= kickoff. The newer Asian totals/handicap research join instead requires a separately frozen forecast <= quoted odds snapshot <= kickoff, with full score distributions. These are different evidence contracts and **must not be silently interchanged**. Historical 1X2 shadow archives cannot be relabeled as Asian quarter-line EV or ROI evidence.

**Next investigation:** inspect actual archive paths and counts via an authorized repository/archive listing; check archive timestamp and model versions, then assess whether the existing 1X2 forward-validation metrics can be reused as a baseline. No claim that real archive rows were fetched or independently verified in this audit.
