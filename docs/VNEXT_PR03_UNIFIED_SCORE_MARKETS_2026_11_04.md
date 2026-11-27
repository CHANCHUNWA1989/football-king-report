# 足球王者 VNext PR-03：統一比分矩陣與市場結算研究引擎

**Scope:** Offline math-only, zero feed/API access, research-only. Stacked on PR #430, which is stacked on PR #429. Original A/B/C predictions, historical archives, live source gates, GitHub workflows and production recommendation settings are unchanged.

## Concrete gap

Current main branch distributes derived probabilities across separate `shadow_forecast.poisson_1x2`, `asian_handicap_research` and `all_market_scenarios` functions. Independent calculations or truncated grids can cause tiny mismatches and lack a reusable complete score-matrix identity for audit. The new sidecar shares one explicit PMF across all three market types.

## Files

- `ops/score_distribution_vnext.py`
- `ops/tests/test_score_distribution_vnext.py`
- `docs/VNEXT_PR03_UNIFIED_SCORE_MARKETS_2026_11_04.md`

## Mathematical contract

- Input: two **unverified, uncalibrated** pre-match expected goals, each finite in [0.1,5.5]; optional **fixed, not fitted** Dixon–Coles low-score rho, default 0.
- Build independent Poisson marginals with a bounded tail and optionally multiply the low-score (0,0), (0,1), (1,0), (1,1) factors, rejecting nonpositive factors. Normalize the finite 2-D matrix, which drives **all markets**; hard fail on nonfinite, negative, ragged or nonnormalized supplied matrix.
- Derive 1X2 `HOME, DRAW, AWAY` by summing corresponding matrix cells, and grade Asian handicap and O/U totals using exact quarter-line splits. Five-grade states: FULL_WIN, HALF_WIN, PUSH, HALF_LOSS, FULL_LOSS.
- Asian handicap uses the existing `asian_handicap_research.quarter_units` parser for strict lines within its legacy research range of +/-5.0, and the test suite checks parity with `asian_handicap_research.grade` for representative scores and lines. Totals use the same exact quarter-unit arithmetic with a distinct 0–20 goal research range; arbitrary non-quarter lines are rejected, never rounded.
- A `score_matrix_sha256` binds the research output's deterministic matrix; not an external evidence attestation. `build_report` atomically fails a whole batch if any market request is invalid, duplicated or carries unexpected quote fields.
- Score settlement is solely **90-minute regulation full-time including stoppage time**; excludes extra time/penalty shootouts and *remaining-only* in-play quarter lines. A sportsbook's actual scope is not established by the function.

## Trust boundaries

**PR-03 is not a calibrated model, data-provider connector, time-certified prediction, sportsbook price, EV evaluator, ROI calculator, or live-betting engine.** No market quote/price input is accepted, no EV is calculated, and `positive_ev_verified=False`, `production_recommendations=DISABLED`, `model_scoring_eligible=False` on success and failure. Returned `RESEARCH_ONLY` denotes algebraic consistency only.

This module must never be called as a substitute for the upstream PR-01 point-in-time/PR-02 event source verification guards. A future independent integration PR is required for any linkage to archived research forecasts, and still cannot promote betting without separately authenticated source and executable quote evidence.

## Acceptance

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

The new synthetic tests target normalized finite PMF, goal tail and extreme score coverage, identical 1X2 aggregation, home/away symmetry, fixed rho0 baseline comparison, existing Asian settlement parity, quarter-line half wins/losses/pushes, O/U complementarity, invalid odds-like fields, atomic HOLD, and absence of positive-EV claims.

GitHub Actions exact-head logs and independent review must be verified before merge. A green CI tests mathematical behavior, **not** true model calibration, profitability or data provenance.
