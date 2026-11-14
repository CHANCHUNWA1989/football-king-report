# Paired Poisson / Dixon–Coles research uncertainty

The optional research pipeline is:

1. Validate target fixture IDs and final-result cohort.
2. Refit Poisson and Dixon–Coles separately at each target's `as_of_utc`, using only historical results recorded before that cutoff.
3. Compare the exact same target IDs, kickoff times, cutoff times and outcomes; fail the entire cohort on missing or duplicate forecasts.
4. Calculate 1X2 accuracy, Log Loss, Brier and calibration bins for both models.
5. Calculate per-fixture paired differences (Dixon–Coles minus Poisson in accuracy, Poisson loss minus Dixon–Coles loss in Log Loss and Brier); positive means Dixon–Coles is better on that metric.
6. For at least 30 paired fixtures, produce reproducible percentile 95% IID bootstrap intervals from 1,000 paired resamples by default.

## Strict limitations

- The 30-fixture threshold is a **minimum for reporting an exploratory interval**, not a claim of adequate statistical power. Real evaluation requires larger prospective cohorts and a predeclared sample plan.
- IID bootstrap assumes independent fixtures; same-team, same-league and same-matchday dependence can narrow intervals spuriously. Future work: league/date cluster bootstrap with adequate independent clusters, out-of-time validation and multiple-comparison controls.
- Calibration bins and ECE are diagnostic and unstable on small samples.
- `evidence/settled.json` does not provide independently verified results for its 82 fixtures. This pipeline has no verified real-match model winner, no bookmaker-executable odds and no proven EV or ROI.
- Local timestamps and boolean flags are not independent time or source attestation. Never automatically promote a model.
- This code does not write to main, execute bets, enable production picks or bypass Issue #439 independent review.

Research outputs remain `HOLD` with `production_recommendations=DISABLED`.
