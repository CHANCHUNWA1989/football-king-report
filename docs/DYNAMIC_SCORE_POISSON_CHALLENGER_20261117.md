# Football-King dynamic score-driven Poisson challenger — 2026-11-17 HKT

**DRAFT ONLY / HOLD / production recommendations DISABLED / positive EV NOT verified.**

## What was actually added

- `ops/dynamic_score_driven_poisson.py` is an **original Python dynamic
  score-driven Poisson** (a simplified GAS-style online rating model), **NOT
  a Bayesian posterior state-space model**, footBayes, Dynamic Bayesian
  Poisson, R/Stan implementation, nor a calibrated production model.
- Each team has latent log-scale attack and defence strengths. Before each
  historical scored match is ingested, old strengths decay towards zero
  with a fixed **180-day half-life**. Once the result is *eligible* and
  observed, its Poisson score residual updates the **home attack/away
  defence** and **away attack/home defence** states. The next forecast uses
  only previously observed results. There is also an updated league-wide
  home/away goal prior.
- Fixed research hypotheses: score learning rate `0.035`, team-state
  half-life `180d`, prior `30` hypothetical league games at home `1.35`
  and away `1.10` goals each. State and score residuals clipped to bounded
  ranges; **no tuning or proven superiority** on the already examined
  2026 holdout. Chosen during this feature work, not independently
  pre-registered before earlier research.
- Exact normalized 15x15 independent conditional Poisson score grid
  produces *one coherent* 1X2 vector, hypothetical totals Over 2.5, 2.75
  and 3.0 settlement masses and home AH quarter line masses, reusing
  existing tested Asian settlement math. This dynamic model does NOT
  model correlated goals, fixture lineups, xG, neutral venue or injuries.
- `predict_offline(payload)` accepts existing strictly validated historical
  native fixture IDs/source namespaces, UTC-aware **result_recorded_utc**
  before a declared target `as_of_utc`, future kickoff, adequate unique
  training matches, and the exact DISABLED contract. If invalid,
  HOLD with no partial rates/probabilities. Even on correct execution,
  HOLD with `positive_ev_verified=false` and zero certified samples;
  caller-supplied timestamps are **NOT independent source verification**.
- `date_only_diagnostic_rates(train, home, away, cutoff_day)` is explicitly
  for older date-only public CSV replay. It uses calendar-day ordering as
  a **surrogate for time evolution, NOT an assertion of true result
  publication or kickoff times**. Never call it a signed pre-kickoff capture.

## Real historical score-only evaluation (separate from engineering test)

`ops/dynamic_2026_date_split_audit.py` shares the same pinned real source
and same **260 full-time 2025 European national-team results / all 186 eligible
2026 outcomes through 2026-10-06**, as previously inspected by research.
This is a **REUSED exploratory 2026 date split**, not fresh prospective
validation or a new untouched confirmation sample.

- Fits original A replica, real Penaltyblog Poisson and real Dixon-Coles on
  **2025 scores only**; dynamic score model updates solely on those
  2025 scores and ages its team states to each 2026 target date. **No
  2026 test score enters ANY model fit.**
- Scores the SAME fixed 186 90-minute outcomes for all models, with
  mean multiclass Brier, log loss and directional 1X2 hit rate.
- Scores **hypothetical** Over 2.75 and home AH -0.25 as five stake-grade
  outcomes, never pretending bookmakers offered those lines/prices.
- A 2,000-draw **paired calendar-day cluster bootstrap** reports exploratory
  95% loss-difference intervals for *dynamic minus Dixon-Coles* in each
  market. An interval excluding zero, if any, still **cannot certify
  superiority** on a previously inspected cohort, given possible
  experiment selection and data limitations.
- Genuine match-date-only CSV provides no independent publisher result
  time, native UEFA ID, pre-match witness, xG or available betting odds.
  Hence **no claims of verified positive EV, ROI or production accuracy**.
- CI `.github/workflows/dynamic-score-poisson-research.yml` runs
  adversarial unit tests (score-driven strength changes, source/identity
  chronology, input immutability, score-grid consistency) and real
  2025/2026 historical results fitting if the pinned Git source is accessible.
  On a missing source, CI fails; do not invent a successful backtest.

## Progression / review blockers

The true deployment-quality next stage still requires new future
pre-kickoff forecasts sealed together across all models at identical native
source identity and time, independently witnessed source/release timestamps,
postmatch official plus independent FT scores, and separately real matched
bookmaker AH/OU price archives. Compare paired Brier/log loss, calibration,
reproducible uncertainty and source rights with independent review.

No main merge, model promotion, money staking, live EV, scheduled betting,
post-hoc tuning of this reused cohort or alteration of frozen 2026-11-15
original predictions is authorized.

## Reproducible commands

```bash
python -m unittest ops.tests.test_dynamic_score_driven_poisson ops.tests.test_dynamic_2026_date_split_audit -v
python -m ops.dynamic_score_driven_poisson --input /path/to/approved-offline.json
python -m ops.dynamic_2026_date_split_audit --output output/dynamic-2026-hold.json
```

## Actual pinned historical-score experiment result — 2026-11-17 HKT

The first actual CI ran to completion on **2026-11-17 00:47 HKT** (GitHub
UTC 2026-11-16 16:47): [Actions run #43911219122](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/43911219122),
exact code SHA `d597ea6069eda92a74868938086bccc880a313ae`,
**success** for both synthetic anti-lookahead checks and true
Penaltyblog 1.13.1 comparison on the pre-existing pinned 2025/2026 scores.

| Model | 1X2 hit | 1X2 Brier | 1X2 log loss | Over 2.75 Brier | Home AH -0.25 Brier |
|---|---:|---:|---:|---:|---:|
| Original A (adapted club formula) | 47.31% | 0.622758 | 1.036047 | 0.673417 | 0.622758 |
| Actual Penaltyblog Poisson | 53.23% | 0.566156 | 0.949444 | 0.659953 | 0.566156 |
| Actual Penaltyblog Dixon–Coles | 52.69% | **0.565359** | **0.947245** | **0.657610** | **0.565359** |
| New original dynamic score-driven Poisson | **41.40%** | 0.643061 | 1.064700 | 0.663012 | 0.643061 |

**Paired dynamic minus Dixon–Coles**, lower is better, 2,000 deterministic
calendar-date cluster resamples on 186 previously inspected matches:

| Market | Brier mean delta / exploratory 95% interval | Logloss mean delta / exploratory 95% interval |
|---|---|---|
| 1X2 | +0.077702 / [+0.020165, +0.137386] | +0.117455 / [+0.021881, +0.206846] |
| Home AH -0.25 | +0.077702 / [+0.016820, +0.141402] | +0.117455 / [+0.022064, +0.205308] |
| Over 2.75 | +0.005402 / [-0.043631, +0.053830] | +0.006155 / [-0.066445, +0.071767] |

**Decision: DO NOT PROMOTE.** The new score-driven dynamic model is worse
on this fixed **reused** historical 1X2/AH cohort, with a modestly inferior
Over-2.75 point estimate. Those CIs are *descriptive*, not proof of stable
superiority or inferiority on a fresh independent prospective cohort.
Do not tune eta/decay/home priors on these 186 already-seen scores and
then call them untouched OOS. Keep original A, Poisson, Dixon–Coles,
Bivariate research predictions and frozen actual prior forecasts unchanged;
no main merge, live signal, positive EV, or money stake.

An independently pre-registered future trial with newly observed
results/real timestamped odds (or an untouched authorized historical source
with real receipt metadata) is needed for any future release decision.
