# Football-King optional time-decay challenger — 2026-11-16

**Research-only / Draft PR #458 / HOLD / production DISABLED / positive EV unverified.**

## Change
- Sidecar `ops/penaltyblog_time_decay_research.py`, without edits to any original A, Poisson or Dixon-Coles sealed vectors, production pipelines, or historical evidence.
- Reuse the existing strict offline Penaltyblog input contract, identity checks, per-match result-recorded times, source namespace, league, and target cutoff.
- At the SAME frozen `as_of_utc` fit unweighted and weighted Poisson OR Dixon-Coles (caller chooses existing model type), using the same eligible rows. No score or market odds from a future fixture are accessed.
- Fixed **xi=0.003 per day**, age=(as_of - historical match kickoff) in days, weight=exp(-xi * age), approximate half-life 231 days. Fixed before testing, not selected for historical profit or hit-rate.
- Output is `HOLD` **even on success** with diagnostic 1X2 probabilities, difference, training count, effective weighted sample size and age range. No bets, Kelly stakes, EV, ROI or production promotion.
- Real optional Penaltyblog v1.13.1 accepts `weights` on Poisson and Dixon-Coles goal model constructors; no external source is copied.
- Separately run equal-weight and weighted forecasts on **truly prospective** licensed, authenticated data, then measure paired Brier/logloss and uncertainty before even considering a model upgrade.

## Security/limitations
This is **not** a data refresh and does not solve the missing November results in the 2026-11-15 8-fixture research cohort (public training stopped October 6). Date weighting cannot make missing matches appear. No automatic online harvesting, no revised historical probabilities, no retroactive success claim and no confidence in an execution price. It does not yet model neutral-venue flags, player availability, injuries or lineup. Those require verified inputs and a separate data contract.

A new GitHub workflow `.github/workflows/penaltyblog-time-decay-research.yml` runs the direct synthetic contract tests and the optional real dependency smoke with fabricated observations. Neither verifies predictive accuracy or profit.

## Offline example
With an existing strict Penaltyblog offline input JSON, change only its `schema` to `football-king-penaltyblog-time-decay-research-v1`; keep `model` as `poisson` or `dixon_coles`, `production_recommendations` as `DISABLED`, and preserve the historical source and cutoff data. Invoke:

```bash
python -m ops.penaltyblog_time_decay_research --input /path/to/research-input.json
```

Do not treat the output as a betting recommendation.

Source: official Penaltyblog weighting documentation at https://penaltyblog.readthedocs.io/en/latest/models/overview.html.
