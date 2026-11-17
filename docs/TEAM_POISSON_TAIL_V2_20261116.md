# Team Poisson probability-core correction — 2026-11-16

Research branch / Draft #458 / HOLD / DISABLED / positive EV unverified.

## Reproduced defect

`private_soccerdata_team_poisson._poisson` put all probability above 12 goals into the exact 12-goal bin, although its own fitted-rate cap is 15. This is a censored distribution, not the intended independent Poisson score model. At high rates it artificially creates tied scores; asymmetric rates also produce incorrect 1X2 probabilities. Synthetic tests failed against an independent 121-term log-PMF (`lgamma`) oracle before this correction.

## Numerical policy and version

- Preserve the same training-day split, team attack/defence shrinkage, rate floors, rate cap 15 and result-availability limitations. No tuning on observed holdout scores.
- The old cutoff is a minimum retained endpoint. Extend the existing PMF recurrence until `P(k+1)/(1-lambda/(k+2)) <= 1e-12`, with ratio below one. Later PMF ratios decrease, so this geometric series bounds the omitted tail.
- Normalize the retained PMF without concentrating the tail at a single score. Rate inputs stay within the model's existing 0–15 domain and support is bounded by 256; invalid/nonfinite inputs fail closed. Float-rounding error is separate from the analytic tail bound.
- New output ID: `retrospective_team_goal_poisson_adaptive_tail_v2`; report `per_team_omitted_tail_mass_bound=1e-12`.
- The dependent approximate DC output becomes `approximate_low_score_dixon_coles_adaptive_tail_v2` and records its base model. CSV comparison outputs expose both changed model versions. This remains an approximate low-score correction, not a new joint DC MLE.

## Evidence boundary

All tests are synthetic. They check 0/low/high rates, exact Poisson mass at 12 goals, symmetric and asymmetric 1X2 against independent log-PMF sums, actual omitted-tail mass, normalization, input immutability, prior-only training, invalid inputs and version propagation. No authorized real cohort was refitted, rescored or used to select this correction. Original A/B/C, external Penaltyblog models, time-decay weights, archived forecasts/results and published historical reports are unchanged. New research reports must retain v2 identities; do not relabel old v1 results.

This fixes a mathematical approximation error, not source rights, external forecast witnesses, result truth, calibration or predictive superiority. Formal model promotion still requires real prospective/OOS evidence, independent human review and #439/#452 clearance. No merge, deployment or wagering is authorized.

## Handoff
- TDD: five initial numerical/version failures and three lineage failures reproduced before their respective fixes.
- 25 related tests passed; full regression 2,895 tests, zero failures, two locally missing optional-dependency skips (penaltyblog RPS / soccerdata constructor); compileall and diff check passed.
- One read-only QA found no actionable issue; independent synthetic checks also confirmed the tail bound across rates/cutoffs. This is not human release approval.
- Only the existing private research core, its dependent version labels/comparison metadata, tests and this document changed; no real cohort was evaluated.
- Exact new commit/CI acceptance is recorded in Draft PR #458. Existing unresolved CI status must not be replaced by an older successful run.
- HOLD/DISABLED/positive EV=False; original production models and archives remain unchanged, no merge/deploy, no verified accuracy/profit improvement.

## DC rho v3 — 2026-11-16 handoff
- Require finite, strictly positive tau factors for all four low scores (0–0, 0–1, 1–0, 1–1), even when a cell never appeared in training; observed-score checks remain.
- Initialize the training log-tau baseline at rho=0 (score=0); retain neutrality unless a feasible candidate strictly improves training likelihood. The existing -0.10 to +0.10 grid, step0.01, is unchanged and not tuned on holdout.
- New ID `approximate_low_score_dixon_coles_admissible_rho_v3`; parent remains Poisson adaptive-tail v2 and existing CSV version mapping propagates v3. No Poisson rates, shrinkage, training folds or fixed forecasts changed.
- TDD reproduced15 failure cases; 30 related tests passed, full regression2,900 tests with zero failures/two locally absent optional-dependency skips; compileall/diff check passed.
- One read-only QA found no actionable correctness issue; it is not independent human approval. Latest commit and exact-head CI acceptance are recorded in Draft PR #458.
- This remains a league-rate approximate correction, not joint DC MLE or proof of superiority. No real-data scoring, archived-result edits, paid APIs, merge/deploy or wagering; HOLD/DISABLED/positive EV=False, #439/#452 and human review remain unresolved.

## DC fixture-rate v4 — 2026-11-17 handoff
- New ID `approximate_low_score_dixon_coles_fixture_rate_v4`: apply tau to the SAME normalized target Poisson cells (H:1–0, A:0–1, D:0–0+1–1), replacing the inconsistent league-rate correction mass.
- Rho still maximizes earlier-training league log likelihood, with the existing grid/neutral-on-ties rule; candidates must additionally have positive finite tau at the fitted target rates. Target outcomes are not used. This is still approximate, not joint DC MLE.
- Poisson v2 only adds capped target rates and four low-cell masses as metadata; three synthetic cohorts matched all prior numerical fields exactly. Four cells are partial model metadata, not a complete betting distribution or executable odds.
- TDD reproduced five numerical/version/valid-input failure cases;34 related tests passed; full regression2,904 tests, zero failures/two local optional-dependency skips (penaltyblog RPS/soccerdata constructor); compileall/diff check passed.
- One read-only QA found no actionable issue;29 tests plus83 synthetic grid/rho comparisons confirmed index alignment and mass conservation. Latest exact-head CI acceptance is recorded in Draft PR #458.
- No real-data evaluation, dependency, API collection, sealed A/B/C/result edits, merge/deploy or wagering. HOLD/DISABLED/EVFalse; source rights, independent witnesses/results, OOS performance and human review remain unresolved.
