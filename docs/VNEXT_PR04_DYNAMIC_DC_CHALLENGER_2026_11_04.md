# 足球王者 VNext PR-04｜即場反勝機率與 Dixon–Coles 低比分研究 Challenger

**2026-11-04 · research only · stacked on Draft PR #431 → #430 → #429**

## Existing evidence and limits before changes

Existing `ops/model_dixon_coles_forward.py` contains a **fixed** rho=-0.05 forward-capture research challenger; its originally sealed A/B/C/protocol files and checksums must remain unchanged. PR #431 adds an uncalibrated shared score-PMF; PR #429/#430 validate point-in-time claimed metadata and two-provider event/VAR assertions but **do not authenticate sources, prove true wall-clock receipt, or authorize market predictions**.

No licensed real-time xG, independently certified live source pair, complete as-of event archive, executable Asian quotes or untouched sufficient prospective holdout has been obtained in this PR. Every model or probability shown is research-only.

## Gap 1: time-varying in-play 1X2 and comeback probability

`ops/inplay_state_challenger_vnext.py` is an **offline, no-network, fixed-coefficient** mathematical sidecar.

Inputs:
- Fixture ID, kickoff UTC, decision UTC, integer elapsed playing minute 0–89, current goals and red cards.
- Pre-match goal rates and claimed sealed model input hash, with `inputs_available <= prematch_forecast <= kickoff - 10 minutes`.
- A matching PR #430 event-consensus artifact of the **same fixture, time, score and red counts**, with `status=RESEARCH_ONLY`, `source_authenticated=False`, `model_scoring_eligible=False`, and a claimed PR #429 evidence-cut digest.

Hard rejection:
- Incorrect fixture, conflicting score/card count, later feed receipt/decision, missing model time, future model input, forecast too close to kickoff, stale match clock, impossible goals or booleans.
- At playing minute >= 90, abstain/HOLD rather than claiming certainty when stoppage time is unknown.
- Arbitrary extra fields such as future outcomes or bookmaker quotes.

Research calculation:
- Remaining fraction `(90-minute)/90` is applied to pre-match full-90-minute expected-goal rates.
- Fixed illustrative score and red coefficients alter remaining intensities, **not fitted** against historical labels and not claimed empirically accurate.
- A finite, tail-controlled independent Poisson **remaining-goal** matrix is shifted by current goals to form the implied full-time score PMF.
- Reuse PR #431's `one_x_two` and `validate_matrix` so probabilities come from the same normalized score distribution, and derive trailing side's comeback-to-win probability from 1X2.
- Stoppage, extra time, penalties and time-varying future attacks are **not modeled**. The output is not a trading signal. Do not confuse as-of self-assertion with authenticated evidence.

Output safety always includes `production_recommendations=DISABLED`, `model_calibrated=False`, `model_scoring_eligible=False`, `positive_ev_verified=False`, `betting_recommendation_allowed=False`.

## Gap 2: development-only Dixon–Coles calibration research

`ops/dixon_coles_challenger_vnext.py` is a **separate model ID**; it does not modify original `model_dixon_coles_forward.py`, its hashed protocol or A/B/C forecasts.

It accepts:
- A complete caller-declared fixture manifest, minimum 30 and maximum 3,000 distinct development fixtures;
- Each row's historical **original as-of goal-rate snapshot**, input hash, pre-match forecast timestamp, kickoff timestamp, final 90-minute score and *result available* timestamp;
- A single declared UTC fit cutoff.

It **hard rejects** any source input later than the claimed forecast, forecast later than kickoff minus 10 minutes, result available after fit cutoff, manifest mismatch, duplicate fixture, wrong score, or inconsistent timestamps. Samples must have completion at least 90 minutes after kickoff (does not authenticate the actual result).

Only the predeclared fixed `rho_grid = [-0.15,-0.10,-0.05,0.0,0.025]` is scored using **in-sample complete-scoreline log loss** with PR #431's same score-matrix algorithm. The winner and a self-asserted development cohort SHA are returned as `DEVELOPMENT_ONLY`, **not OOS calibration**. The future-only `shadow_forecast` requires `fit_cutoff < new source availability <= new prediction <= new kickoff - 10 minutes`, and uses the frozen selected rho. It cannot reconstruct historical archived probabilities.

There is no independent external witness for source timestamps, completeness manifest, label truth or its hash, so this is **NOT a verified prospective model**. Separate future PR must collect truly time-attested paired A/B/C/market forward cohorts and use Brier/Log Loss/calibration + confidence intervals before any statistically meaningful claim.

## Tests and acceptance

Added:
- `ops/tests/test_inplay_state_challenger_vnext.py` including 0–2 at minute 45 vs minute 85, trailing-home/trailing-away, red effects, inconsistent event state, forged certification, late input, invalid clock, stoppage HOLD, PMF mass, deterministic replay.
- `ops/tests/test_dixon_coles_challenger_vnext.py` including complete 30-row synthetic cohort, frozen prospective rho, temporal leakage, future result, invalid digest/schema, duplicate and cherry-picked/missing manifest, and safety status.

Repository CI contract:
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

Run on exact PR head and examine raw logs. All passing tests demonstrate *logic and guard behavior only*. Do not merge without independent review of this PR and all upstream stacked PRs, and do not bypass `DISABLED/HOLD` on any research report.

## Unfinished / external prerequisites

1. Independently authenticated provider/source families, enforceable licensing, correct material event clocks and independently pinned append-only evidence.
2. Real as-of, fit-cutoff-observed training corpus with authentic original pre-match rates and fully matched, verified regulation-time results.
3. Validated time-varying hazard coefficients (and missingness masks) rather than the fixed illustrative values.
4. True prospective untouched holdout, signed frozen forecasts, same-time comparator, paired uncertainty intervals.
5. Externally licensed, original execution-time Asian/O-U odds and market settlement scope; NO market edge / CLV / EV / ROI can currently be certified.
