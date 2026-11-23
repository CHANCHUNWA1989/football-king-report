# Scoped scoringrules CRPS reuse

- Upstream: https://github.com/frazane/scoringrules
- Pinned commit: `d4c3b535d7e724cb0a7c316ff15f60e75fc45772`
- Source: `scoringrules/core/crps/_approx_w.py::_crps_ensemble_nrg_w` (blob `29c7ce621568f2602dc06c8c35ccbf3a537bb063`); public contract in `scoringrules/_crps.py::crps_ensemble` (blob `efab5b62c523ae5eead45567c1970347a6935d49`).
- License: Apache-2.0, Copyright 2023 Francesco Zanetta. Complete upstream text is retained in `LICENSE`; the pinned upstream tree contains no separate NOTICE file.
- Adapted location: `ops/case_goal_market_scoring.py::_crps` and `goal_distribution_scoring`.

Modified from the weighted ensemble energy algorithm to score the existing bounded integer total-goals and home-minus-away goal-margin PMFs. Standard-library `math.fsum` replaces array backends. Inputs reject boolean/nonfinite/negative probabilities, noninteger support/observations and non-normalized mass. Only local floating-point residue is normalized; source PMFs and forecasts are not changed. No dependency, source dataset or provider request is added.

CRPS is E|X-y| minus half E|X-X'| for two independent draws from the forecast PMF. This uses the exact weighted empirical-distribution energy form, not the fair finite-sample estimator. Scores are in goals and are not normalized 1X2 RPS/Brier values. They must be compared on the same target and same cases. An observation outside retained support still has a finite distance score; its support status is explicit. All scores refer to the retained, conditioned Poisson grid and unverified candidate outcomes, not the untruncated original distribution or a newly sealed prediction. No baseline superiority, calibration, market odds, EV or profitability is certified.
