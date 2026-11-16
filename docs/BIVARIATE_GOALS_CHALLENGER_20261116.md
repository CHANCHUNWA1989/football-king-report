# Football-King | Bivariate Poisson 3-market challenger (2026-11-16 HKT)

Status: **RESEARCH ONLY / DRAFT / HOLD / production DISABLED / EV unverified**.

## Goal and selection

The user's requested "best" model is evaluated as a *challenger hypothesis*, not established as
superior by model popularity. Bivariate Poisson is the first practical fit for the current
Python Penaltyblog 1.13.1 offline stack, retaining a full joint exact-score distribution for
all three markets in one source of truth. It models correlated match goals, unlike independent
Poisson, and does not need any unverified external feed to execute on synthetic research rows.

The alternative dynamic Bayesian family is supported by R/Stan `footBayes` 2.1.0, but
would add a separate runtime, model-prior design, source contract, Stan build, convergence
diagnostics, and per-fold posterior predictive validation. It is deliberately NOT claimed as
added, fitted, or shown to improve predictions here.

## Files and contract

- `ops/penaltyblog_bivariate_goals_challenger.py`: isolated adapter to the **actual optional**
  `penaltyblog.models.BivariatePoissonGoalModel`. Runs two independent fits over the same
  provided, strictly pre-cutoff matches: baseline equal weights and fixed chronological
  `exp(-0.003 * age_days)`. The xi is only a hypothesis, not tuned on the evaluation holdout.
- Input schema: `football-king-bivariate-goals-challenger-v1` with exact fields
  `schema`, `production_recommendations="DISABLED"`, `model="bivariate_poisson"`,
  `as_of_utc`, `target_fixture`, `historical_matches`.
  Reuse existing offline bridge's event identity, namespace, league, scores, kickoff and
  result-recorded-before-as-of validation. Validation aliases `model` to Poisson
  *only inside a temporary validation copy*; the fitted model is ALWAYS bivariate.
- Output: unweighted/time_weighted 1X2, settlement mass for **Over 2.5, 2.75 and 3.0**,
  plus **home AH -1.0 through +1.0 in quarter increments**. The five mutually exclusive
  stake outcomes are full_win, half_win, push, half_loss, full_loss. Each line's
  probabilities sum to one from the SAME normalized 15-by-15 exact-score matrix.
- No actual bookmaker price is sourced, so there is no EV, staking advice, positive-EV
  certificate, simulated profit, or production recommendation.
- Unit tests verify score-grid/1X2 consistency, Asian split stake (including O2.75
  half-win, AH -0.25 half-loss), invalid inputs, same-instant time zones, duplicate
  JSON keys, no model execution with late results, and no partial output on failure.
- Dedicated workflow validates pure synthetic contracts and **real installed
  Penaltyblog 1.13.1 fitting on synthetic matches**. Even real dependency tests are
  not actual out-of-sample performance evidence.

## Reproducible local call

```bash
python -m ops.penaltyblog_bivariate_goals_challenger --input bivariate.json
```

Before making real data research statements, require authentic licensed fixture/results
data, true result-publication dates, lineup/roster and match identities, fixed-before-kickoff
time, two independently checked official final results, and honest chronological holdout.
Compare paired log loss and multiclass Brier for 1X2, plus proper market probabilities
and realizable quote-time odds (when obtained). Keep original A/Poisson/DC snapshots sealed
and unchanged.

Current prior 2026-11-15 eight-UEFA-match cohort is NOT rescored; its historical
data stopped October 6 and cannot establish superiority for any new challenger.

Official model documentation:
- https://docs.pena.lt/y/models/bivariate_poisson.html
- https://penaltyblog.readthedocs.io/en/latest/models/football_prob_grid.html
- https://cran.r-project.org/web/packages/footBayes/index.html
