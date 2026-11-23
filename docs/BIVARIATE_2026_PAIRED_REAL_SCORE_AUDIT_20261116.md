# Bivariate Poisson — 2026 real-score paired exploratory date-split

**2026-11-16 HKT. Draft PR #487. HOLD / production DISABLED / positive EV unverified.**

## Purpose

Extend the existing historical UEFA-national-team analysis to a genuine matched
2025/2026 **score-only retrospective**. All tested models receive the SAME 2025
training rows and are scored against the SAME 2026 real full-time results.

- Source: previously pinned public `martj42/international_results` history with
  blob hash checked by the preexisting `_read_source` pipeline.
- Train: **260 games dated 2025**. 2026 observed goals are NEVER inputs to fit.
- Test: **186 qualifying games dated 2026-01-01 through 2026-10-06**;
  no cherry-picked profitable or successful fixtures.
- Five model variants: existing adapted original A; actual Penaltyblog 1.13.1
  Poisson, Dixon-Coles, Bivariate Poisson; Bivariate Poisson weighted at
  fixed xi=0.003 per day (anchored to Jan 1, 2026). Model fit happens once
  on 2025-only results; this is **NOT rolling refit** or independently
  witnessed prospective forecast.
- Three PREDECLARED hypothetical markets: 1X2, **Over 2.75**, **home AH -0.25**.
  The same observed score is graded consistently for all five variants.
  Reuse the original A's 2025 role shrinkage rates and previous exact
  Asian settlement baseline; challenger models use their own predicted
  normalized joint score grids, checked against predicted 1X2.
- Metrics: paired mean Brier and log loss, plus top-1 1X2 directional hit rate.
  Score five-grade AH/OU and three-class 1X2 separately. Compare each
  model to a 2025-only Jeffreys-smoothed market outcome-frequency baseline.
  No chosen retrospective "optimal threshold", betting odds, profits,
  Kelly criterion, or claimed positive EV.
- Test quality: adversarial synthetic unit tests verify 2026 score never enters
  fit, duplicate/invalid date and score reject, same observations for every
  model and every hypothetical market; live CI installs real Penaltyblog
  and reads the pinned authentic historical-source bytes.

## Added descriptive paired uncertainty gate

- `ops/bivariate_paired_uncertainty.py` compares (1) **unweighted bivariate minus
  Dixon–Coles** and (2) **fixed-decay bivariate minus unweighted bivariate**,
  for the same three prespecified markets and both Brier and log loss.
- Pairing is fixture-by-fixture. A negative delta means the first model scored
  better. 2,000 deterministic percentile resamples use **calendar-date
  clusters**, not naive independent same-day fixtures (RNG seed 20261116).
- Each cluster draw retains both models' paired losses for all games on its day.
  Reports the actual mean paired loss difference, 95% interval, and whether
  the interval contains zero. Less than five distinct match dates yields
  **no interval**, not a fabricated claim of certainty.
- The intervals are **exploratory**: model selection has already seen this
  186-match holdout, dates are not independent prospective forecast witnesses,
  and resampling dates does not solve source/publication-time uncertainty.
  Even a negative interval excluding zero **cannot promote** a model.
- Fail-closed input validations now independently reject non-finite,
  negative or non-normalized market probabilities before uncertainty computation.
- No extra external results, odds, quote timestamps, xG or individual bets are
  collected. `model_promoted=false` and `positive_ev_verified=false` are
  permanent for this research output.

## Key scientific limitation

The **same 186-match 2026 holdout was already analysed earlier in the
Football-King project**, so it is not an untouched fresh holdout for choosing
the new bivariate model. The upstream CSV contains match dates, **not**
original result-publication timestamps or verified kickoff instants. Treat
this only as exploratory model diagnostics and regression comparison:
no claim of 2026 live recommendation, calibration, accuracy advantage,
external independent provenance, EV, ROI, legal quote rights, or deployment.

Do not rewrite the November 15 actual prospective 8-match predictions or
merge these results into that evaluation. Independent confirmation requires
NEW fresh pre-kickoff forecasts from all models, frozen together with
authenticated 2-source results and matched timestamped bookmaker prices.

## Commands

```bash
python -m unittest ops.tests.test_bivariate_real_2026_paired_oos -v
python -m ops.bivariate_real_2026_paired_oos --output output/real_bivariate_2026_date_split.json
```

Only research CI may fetch this explicitly pinned public historical source.
The output format and strict full-cohort acceptance are documented in
`.github/workflows/bivariate-2026-real-date-split.yml`.
