# Football King | Positive-EV recommendation policy

This is a **research-only** system. All betting recommendations remain disabled.

## Screening rules (initial conservative defaults)

- Require an observed, timely **actual decimal price** of at least **1.80**. A de-vigged consensus implied probability is **not** a tradable quote.
- Require an independently supported probability estimate with a **conservative lower confidence bound**. A raw or uncalibrated model probability is not enough.
- The conservative expected value must be at least **+3%**. The formula `EV_lower = p_lower * decimal_odds - 1` only applies to **binary full-win/full-loss** markets with no push, half-win or half-loss. Asian quarter spreads and goal totals require the full settlement distribution, with net expected return `EV = (odds-1)*(P_full_win + P_half_win/2) - P_half_loss/2 - P_full_loss`. A caller-supplied lower bound or positive theoretical calculation is not independent certification.
- Require a quote no older than **120 seconds**; stale, missing, invalid, suspended or unexecutable prices are `HOLD`.
- The independent provenance, calibration and bookmaker-execution verification layers are not implemented. Even a mathematical screen pass returns **RESEARCH_ONLY** and **never** authorizes a stake.

Example: price 1.90, model estimate 70%, conservative probability 63%.
Raw EV = +33%; conservative EV = +19.7%. This passes the *mathematical research screen* if the quote is fresh, but does **not** establish positive EV in real betting until the probability bound and executable quote are independently authenticated.

Counter-example: price 1.30 and estimated win probability 85%. Raw EV = +10.5%, but the fixed 1.80 minimum price excludes it. The user may request a different price floor after validation.

These are provisional screening thresholds, not proven optimal values or guarantees of profitability.

## Reporting discipline

The research shortlist can display directional observations, **not betting picks**. Public outputs must show `value_recommendation_count=0` and `production_recommendations=DISABLED` until a separate independently authenticated approval mechanism exists. No implied fair-price inversion (`1 / market_probability`) may be presented as a currently executable bookmaker quote.

Implementation: `ops/value_ev_policy.py`; release guard: `ops/release_guard.py`; tests: `ops/tests/test_value_ev_policy.py`.

## Quarter-goal market research routing (draft PR, not merged)

- `ops/value_research_pipeline.py` sends labelled Asian handicaps to `ops/asian_threeway_ev_research.py`; it needs a valid three-way probability vector and supports only -0.5 to +0.5. Deeper handicaps require the **full score-margin distribution**.
- Labelled goal totals (including `over_2_5`, `under_2_75`, `asian_totals`, and `totals`) are sent to `ops/total_goals_ev_research.py`. A scalar binary over/under probability or a 1X2 vector is not sufficient for exact Asian totals unless a fully supported grade distribution is provided separately. This draft requires an **integer total-goals distribution**, with quarter-goal settlement, including pushes and half-outcomes.
- Missing total-goals distribution, missing or conflicting OVER/UNDER selection, misaligned line, missing actual quote proof, missing conservative probability evidence, stale quoted price or unsupported alias must remain HOLD. A declared `calibrated=true` or `fresh_odds=true` is not independently authenticated evidence.
- Even when hypothetical mathematical screening is positive, the research pipeline reports `research_candidate=false` for both Asian spread and total-goal markets, `production_recommendations=DISABLED`, no approved stake and no certified ROI.
- These patches are isolated to a **Draft PR**; unchanged production workflows and earlier immutable evidence remain protected. They do not automatically validate new market-name aliases or upgrade confidence levels.
