# Football King | Positive-EV recommendation policy

This is a **research-only** system. All betting recommendations remain disabled.

## Screening rules (initial conservative defaults)

- Require an observed, timely **actual decimal price** of at least **1.80**. A de-vigged consensus implied probability is **not** a tradable quote.
- Require an independently supported probability estimate with a **conservative lower confidence bound**. A raw or uncalibrated model probability is not enough.
- The conservative expected value must be at least **+3%**: `EV_lower = p_lower * decimal_odds - 1 >= 0.03`.
- Require a quote no older than **120 seconds**; stale, missing, invalid, suspended or unexecutable prices are `HOLD`.
- The independent provenance, calibration and bookmaker-execution verification layers are not implemented. Even a mathematical screen pass returns **RESEARCH_ONLY** and **never** authorizes a stake.

Example: price 1.90, model estimate 70%, conservative probability 63%.
Raw EV = +33%; conservative EV = +19.7%. This passes the *mathematical research screen* if the quote is fresh, but does **not** establish positive EV in real betting until the probability bound and executable quote are independently authenticated.

Counter-example: price 1.30 and estimated win probability 85%. Raw EV = +10.5%, but the fixed 1.80 minimum price excludes it. The user may request a different price floor after validation.

These are provisional screening thresholds, not proven optimal values or guarantees of profitability.

## Reporting discipline

The research shortlist can display directional observations, **not betting picks**. Public outputs must show `value_recommendation_count=0` and `production_recommendations=DISABLED` until a separate independently authenticated approval mechanism exists. No implied fair-price inversion (`1 / market_probability`) may be presented as a currently executable bookmaker quote.

Implementation: `ops/value_ev_policy.py`; release guard: `ops/release_guard.py`; tests: `ops/tests/test_value_ev_policy.py`.
