# VNext PR-03 | Unified full-time score / Asian market distribution

Status: **draft, offline mathematical research only** (2026-11-04).
Stacked dependency: PR #429 (PIT cut) → PR #430 (two-provider live-event audit) → PR-03.
This PR has **no live or pre-match provider ingestion**, no score-to-betting integration, and no change to original A/B/C model, public recommendations, deployment, secret permissions, or feature weights.

## Gap and scope

Earlier research files `ops/asian_handicap_research.py`, `ops/all_market_scenarios.py`, and `ops/over_under_25.py` calculate related market probabilities via separate paths. The new `ops/unified_score_distribution_vnext.py` defines one reproducible, bounded **independent-Poisson pre-match research grid**, from which **all three markets** are derived without re-estimating rates:

- 1X2 from partition of score cells `h>a, h==a, h<a`.
- Asian handicap five grades (FULL_WIN / HALF_WIN / PUSH / HALF_LOSS / FULL_LOSS) applied to **the selected team** for whole-match FT 90-minute score.
- Asian total five grades (OVER / UNDER) on the **same full-time total goals**.

A quarter line is represented exactly in integer quarter-goal units, split into two equal stakes at neighboring half-goal lines where necessary. `+0.25` = `0` and `+0.5`; `-0.75` = `-1.0` and `-0.5`; `OVER 2.25` = equal stakes at 2 and 2.5. No rounding of unsupported lines.

The Poisson grid expands independently up to a 65 × 65 hard maximum (normally far smaller) until each marginal's omitted tail is at most 2.5e-11; union bound on the missing joint tail is <= 1e-10. The included grid is explicitly normalized, nonnegative and validated; matrix hashes are deterministic.

## Admissibility

`research_prematch` **only accepts**:
1. a strict, research-only forecast structure with original model ID and goal rates;
2. PR #429's **PREMATCH** cut with exact fixture identity and a separately supplied trusted digest pin;
3. `cut.decision_utc <= forecast.forecast_utc < kickoff_utc`;
4. `production_recommendations = DISABLED`, no result labels, sportsbook quotes, or exotic fields.

If anything is missing or inconsistent, the entire scenario returns `HOLD` and no subset is used. Success is `RESEARCH_ONLY`, **not source authentication or model eligibility**. Note: `verify_pinned_cut` only compares supplied hashes. A caller copying the digest from the cut itself does **not** demonstrate a genuinely independent archive or wall-clock attestation. Those require future separately approved infrastructure.

The output carries `score_matrix`, `matrix_sha256`, exact market probability partitions, a truncation bound, and unconditional:
- `model_scoring_eligible = false`
- `source_authenticated = false`, `model_calibrated = false`
- `bookmaker_quote_authenticated = false`, `positive_ev_verified = false`
- `production_recommendations = DISABLED`, `recommended_bets = []`.

**There is no quoted price, hypothetical model-derived EV, ROI or staking.** Existing `ops/*` math is unchanged, and the new functions do not run in deployed workflows.

## Limits

- This is a pre-match **independent Poisson** research baseline; Dixon–Coles, correlations, team strengths, dispersion, calibration and state-based in-play intensity belong to separate future challenger PRs.
- A full-time Asian market and an in-play **remaining-goals** market are different contracts. The module accepts no in-play cut and must not be reused for in-play prices by replacing goal rates without an independently reviewed settlement contract.
- Football bets commonly settle at end of regular 90 minutes plus stoppage, excluding extra time and penalty shootouts. This module represents only mathematical FT goal counts; not a sportsbook contract or fixture settlement proof.
- `PIT` hash pin and fixture timestamps are internal claims, not independent source/time authentication.
- No claim of actual accuracy improvement or positive EV.

## Tests

`ops/tests/test_unified_score_distribution_vnext.py` includes positive, adversarial and algebraic cases:
- zero/high/invalid Poisson rates, bounded tails, matrix normalization, ragged/invalid input, HOME/DRAW/AWAY symmetry;
- handicap `-0.75`, `-0.25`, `+0.25`, `+1.25`, full/half/push results; totals `2.25`, `2.5`, `2.75`;
- five-grade mass conservation and opposing side complement symmetry;
- one matrix reused for every market;
- missing or wrong evidence pins, mixed fixtures, late/in-play data, result/odds injection and enforced `DISABLED`.

CI:
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

Evidence of passing tests is **not** evidence of reliable predictions or sports betting profitability. Do not merge without exact PR head CI success, independent review, dependency approval and rollback plan.
