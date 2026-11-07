# Scoped penaltyblog reuse

- Upstream: https://github.com/martineastwood/penaltyblog
- Pinned commit: `6870f0e762e9cba35fa722dc14a8daeaf8bc6134`
- Algorithm references: `penaltyblog/metrics/metrics.pyx` (`compute_rps_array`), `penaltyblog/metrics/rps.py`, and `penaltyblog/implied/implied.py` (`_power`).
- Licence: MIT, Copyright 2021 Martin Eastwood; permission text retained in `LICENCE`.
- Adapted locations: `ops/market_shrinkage.py:ranked_probability_score` and `ops/odds_market.py:_power_probabilities`.

The cumulative-forecast versus cumulative-outcome squared-error algorithm is adapted to a standard-library-only scalar 1X2 function, fixed home/draw/away ordering, and the existing strict numeric/outcome validation. Accepted probability-sum rounding residuals are normalized locally; score normalization is number of classes minus one. Existing shrinkage and daily reports reuse this same function; paired model/market evidence now exposes descriptive RPS on the same settled cases.

The power implied-probability algorithm solves `sum((1 / odds_i) ** k) = 1`. It is adapted to standard-library bisection on the upstream bracket [0, 100], bounded to 80 iterations with a 1e-12 mass tolerance and local final normalization. Existing price, three-outcome, overround, and timestamp validation runs first. The original multiplicative consensus remains the baseline; the power consensus is an additive diagnostic on identical surviving bookmakers. Incomplete numerical alternatives remain HOLD with null values, never substituted from another market or book.

No NumPy/Cython/SciPy dependency, scraper, live API, model, dataset or third-party performance claim is copied. MIT software permission does not grant rights to any external football or bookmaker data. Probability scores and normalization differences do not establish executable odds, calibration, positive EV or profitability.
