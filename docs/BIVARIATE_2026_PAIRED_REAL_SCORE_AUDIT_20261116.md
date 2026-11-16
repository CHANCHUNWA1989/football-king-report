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
