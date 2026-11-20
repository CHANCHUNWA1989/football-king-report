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


## Actual archived evidence located (follow-up)
Directly fetched **default-branch `evidence/settled.json`**, not merely its README reference. Its `checked_utc` is `2026-11-04T22:32:48.344964+00:00`. It contains **77 settled research samples** distributed as: Bundesliga 36, Championship 16, EPL 9, La Liga 8, Ligue 1 5, Serie A 3. All 77 have `market_utc <= forecast_utc < kickoff_utc` by parsed timestamp comparison. **Zero** of the 77 have `fixture_result_source_independently_verified: true`. This is a narrow inventory/chronology check, not a full replay of provenance or independent result verification.

Sample schema: `key`, `league`, `kickoff_utc`, `forecast_utc`, `market_utc`, `y` (1X2 outcome), `p` (three-way model probabilities), `m` (three-way de-vigged market probabilities), `fixture_result_source_independently_verified`, `production_recommendations`, and optional `ab`/`ab_model`. This is **not** the Asian settlement join schema: no score probability distribution, executable odds, or per-quote Asian line. Therefore do not map these rows into `join_frozen_forecasts` or compute Asian EV/ROI.

The earlier statement that actual archived forecasts were not located is superseded by this direct evidence. Next blocker: independently validate outcome provenance and source snapshot immutability; then calculate baseline 1X2 calibration metrics with explicit unverified-result warnings. **No production activation.**


## Baseline 1X2 scoring from actual archived records
Calculated directly from the 77 rows of default-branch `evidence/settled.json` (archive checked `2026-11-04T22:32:48.344964+00:00`). Each row has `y` in 0/1/2, and three-element `p` (model) and `m` (de-vigged market) vectors. For each row, multiclass Brier = sum of squared deviations from the one-hot outcome; log loss = -ln(probability assigned to the observed outcome). All 77 rows had usable vectors and outcome indices.

| Metric (lower is better) | Model | Market baseline | Model minus market |
|---|---:|---:|---:|
| Mean multiclass Brier | 0.6416477882 | 0.5894397518 | +0.0522080365 |
| Mean natural-log loss | 1.0590734325 | 0.9865012992 | +0.0725721333 |

**Interpretation:** On this specific archived sample, the model underperforms the market on both proper scoring rules. This is a descriptive comparison, **not** independently validated performance or an estimate of long-run profitability. All 77 archived outcomes are marked as not independently verified; archive-level `results_independently_verified=false`, `profitability_verified=false`, `production_recommendations=DISABLED`. There are no executable bookmaker prices, so ROI, CLV, and Asian EV are not computable from these rows. No confidence interval, leakage audit, or bootstrap has been performed.

**Decision:** retain HOLD/DISABLED. Prioritize independent result source validation and audit whether the 77 settled rows were prospectively frozen. Do not claim positive EV.


## League-level error diagnosis (77 archived samples)
Computed directly from the same 77-row `evidence/settled.json`, with multiclass Brier and natural-log loss as defined above. Deltas are **model minus market**; positive means model worse.

| League | N | Model Brier | Market Brier | Delta | Model log loss | Market log loss |
|---|---:|---:|---:|---:|---:|---:|
| Bundesliga | 36 | 0.7011 | 0.6411 | +0.0600 | 1.1447 | 1.0595 |
| Championship | 16 | 0.6653 | 0.6124 | +0.0529 | 1.0920 | 1.0229 |
| EPL | 9 | 0.6277 | 0.5472 | +0.0806 | 1.0272 | 0.9248 |
| La Liga | 8 | 0.3925 | 0.3541 | +0.0385 | 0.7182 | 0.6521 |
| Ligue 1 | 5 | 0.5663 | 0.5897 | -0.0234 | 0.9595 | 0.9797 |
| Serie A | 3 | 0.6337 | 0.6015 | +0.0322 | 1.0262 | 1.0047 |

Five of six leagues show higher model error than the market. Ligue 1 is the only exception but contains just **five** samples, insufficient to establish an advantage. Bundesliga (36) and Championship (16) account for 52/77 observations, so aggregate error is not a league-balanced estimate. EPL has the largest observed Brier disadvantage (+0.0806) but only nine matches. **Do not** use league rankings to optimize strategy, pick bets, or claim statistical significance; this is exploratory diagnosis on unverified outcomes.

Recommended next evidence gate: verify final scores against independent provider records, verify prospectively frozen timestamps/model provenance, then compute time-blocked league-level confidence intervals on a larger untouched sample. Remain HOLD/DISABLED.


## Result provenance tracing (follow-up)
Inspected actual default-branch `ops/forward_validation.py`. Its `build_index` accepts the public report, optional `football-king-single-source-finished-results-1` records, and cached free result candidates; it explicitly requires `fixture_result_source_independently_verified=False` and writes settled rows with that flag false. Thus the archived 1X2 outcomes are **research-grade source candidates**, not independently authenticated final scores. Source fixture binding is validated internally when available, but is not necessarily serialized into the settled evidence row.

Directly checked all 77 existing `evidence/settled.json` samples: **0/77** include `source_fixture_identity`, **0/77** include `fixture_result_source`, and **0/77** include `model_artifact_sha256`. Missing fields alone do not establish that the original upstream source never existed: they establish that **the settled evidence artifact does not carry those attestations**. Updated the read-only audit and unit test to report source-identity coverage separately.

The required next gate is to retain explicit upstream source references and provider IDs in a new prospectively captured artifact (with privacy/licensing review), independently compare outcomes, and freeze the model artifact hash before kickoff. **Do not backfill a source attestation based solely on existing outcome labels.**
