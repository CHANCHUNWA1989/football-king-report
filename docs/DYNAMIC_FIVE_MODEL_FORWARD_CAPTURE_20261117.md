# Football-King | Five-model future match shadow capture (17 Nov 2026 HKT)

**Draft PR #490 stacked on Draft PR #487, research-only HOLD/DISABLED.**

## Scope delivered

This is **NOT** a new model selected for production. The previously implemented
score-driven dynamic Poisson performed **worse** than Dixon-Coles over the
already-inspected 2026 186-game public score-only cohort (1X2 Brier 0.643061
vs DC 0.565359; 1X2 hit 41.40% vs 52.69%). The purpose of this feature is
to gather a genuinely NEW before-kickoff local comparison, not to tune or
cherry-pick the model after seeing scores.

- `ops/dynamic_score_driven_poisson.py`: dynamic states evolve in
  **historical kickoff order** rather than the local GET receipt timestamp.
  The existing strict `_validate` requires **ALL historical results to
  have been received before the current target cutoff**, so no later
  scores become eligible. This corrects the common scenario in which a
  one-GET source first observes all already finished matches simultaneously.
  Historical kickoff and first-seen clocks are not independently certified.
- `ops/dynamic_five_model_prematch_gate.py`: accepts a local successful
  original A/Poisson/DC/Bivariate four-model research envelope, double-checks
  native home/away/league/event source IDs, historical count, same
  cutoff, clock monotonicity, remaining kickoff safety buffer and valid
  pre-cutoff probabilities, then fits fifth score-driven dynamic model
  on EXACT same existing historical source/native ID list. No partial
  fifth-model output if any gate fails. Even success produces HOLD and
  `certified_prospective_samples=0`.
- `ops/bivariate_four_model_prematch_gate.py` now emits native home/away
  IDs inside the four-model local envelope to allow genuine fifth-stage
  cross-checking; this does not edit the original A input or predictions.
- `ops/live_bundesliga_three_model_probe.py --with-dynamic` implies
  `--with-bivariate`, reuses the original V4.1 algorithm, the
  same one-GET OpenLigaDB current response and the same
  pre-match cutoff, and attempts up to 2 genuine future fixtures.
  Success provides five core 1X2 versions, dynamic hypothetical
  Over 2.75 and home AH -0.25 masses and observed local completion
  time. Fixed-decay bivariate can still be a diagnostic shadow but
  should not be silently counted as an extra independent model.
- `.github/workflows/dynamic-five-model-forward.yml`: one strict
  synthetic unit-test job and one opt-in PR-triggered genuine future
  source/real Penaltyblog fitter job; checks the pinned gateway zip by
  SHA256 before running. Failure to find a true future match or
  match source/native IDs **fails the job**, not retroactively labels
  a finished fixture a prospective result. The workflow only archives
  a short-lived, UNVERIFIED local source/time research artifact on success.

## Critical limitations

- Valid execution does **not** independently authenticate publisher
  timestamps, first-publication of results, actual sportsbook offered
  Asian/total lines or price quotes, calibrated profit/ROI/EV,
  lineup/xG, third-party time stamp or official+secondary FT result.
- Some source rows may not have source-native fixture IDs required for
  the same A-vs-challenger training set; this **must BLOCK** five-model
  completion even if previous three-model output is available.
- `pull_request` and manual `workflow_dispatch` are NOT a periodic
  service. No recurring monitoring/automatic wagers were created here.
- An isolated future local result is not yet *certified prospective*
  evidence; a separate independent immutable timestamp/witness and
  postgame two-source result match are needed for real OOS scoring.
- All observations remain `status=HOLD`,
  `production_recommendations=DISABLED`,
  `positive_ev_verified=false`, `model_promoted=false`,
  `certified_prospective_samples=0`. Do not merge to main or alter
  previous sealed A/Poisson/DC forecasts.

## Tests and next acceptance gate

Adversarial tests should catch equal source GET timestamp but different
historical match times, overwritten source/native IDs, missing results,
untrained teams, cutoff crossing, late fourth/fifth model execution,
probability vector errors and output mutation.

Then take a **new**, genuinely before-kickoff captured, source-readable
fixture ID and five probability vectors. Later, independently verify
90-minute scores at 2 trusted sources and score all original frozen
probabilities with matched Brier/log loss, date-cluster uncertainty,
calibration, and separately verified timestamped market odds. If there
is no eligible forward capture, the correct result is BLOCKED, not
a made-up model win.
