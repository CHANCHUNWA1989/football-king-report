# Scoped penaltyblog reuse

- Upstream: https://github.com/martineastwood/penaltyblog
- Pinned commit: `6870f0e762e9cba35fa722dc14a8daeaf8bc6134`
- Algorithm references: `penaltyblog/metrics/metrics.pyx` (`compute_rps_array`), `penaltyblog/metrics/rps.py`, `penaltyblog/implied/implied.py` (`_power`), and `penaltyblog/models/football_probability_grid.py` (`FootballProbabilityGrid.btts_yes`, `btts_no`, `_sum_mask`, `exact_score`).
- Licence: MIT, Copyright 2021 Martin Eastwood; permission text retained in `LICENCE`.
- Adapted locations: `ops/market_shrinkage.py:ranked_probability_score`, `ops/odds_market.py:_power_probabilities`, and the BTTS/exact-score projections in `ops/case_goal_market_scoring.py:score_goal_markets`.

The cumulative-forecast versus cumulative-outcome squared-error algorithm is adapted to a standard-library-only scalar 1X2 function, fixed home/draw/away ordering, and the existing strict numeric/outcome validation. Accepted probability-sum rounding residuals are normalized locally; score normalization is number of classes minus one. Existing shrinkage and daily reports reuse this same function; paired model/market evidence now exposes descriptive RPS on the same settled cases.

The power implied-probability algorithm solves `sum((1 / odds_i) ** k) = 1`. It is adapted to standard-library bisection on the upstream bracket [0, 100], bounded to 80 iterations with a 1e-12 mass tolerance and local final normalization. Existing price, three-outcome, overround, and timestamp validation runs first. The original multiplicative consensus remains the baseline; the power consensus is an additive diagnostic on identical surviving bookmakers. Incomplete numerical alternatives remain HOLD with null values, never substituted from another market or book.

BTTS sums the score-grid cells where both home and away goals exceed zero; its complement is the NO probability. The NumPy mask/cache is adapted into the existing standard-library grid traversal and `math.fsum`. Only the already validated original A goal-rate reconstruction is used. The existing controlled-case replay carries this additional derived field without another source request or CLI verifier invocation. Binary Brier means the single-positive-class squared error, not the sum of two class errors. The result is not an originally sealed BTTS forecast, authenticated result or bookmaker quote, and all recommendation gates remain disabled.

The `exact_score` grid lookup is adapted to the current independent-Poisson grid. A local extension ranks five cells by unrounded probability, breaking exact ties by ascending home then away goals. Top-five probabilities keep their full-grid mass; remaining in-grid mass is explicit. Unlike the upstream out-of-grid zero convention, our unverified candidate score gets null probability/loss beyond the retained grid, since omitted Poisson support is not evidence of an impossible result. The fixed ranking is independent of the observed candidate score and is not a sealed correct-score forecast or recommendation.

No NumPy/Cython/SciPy dependency, scraper, live API, model, dataset or third-party performance claim is copied. MIT software permission does not grant rights to any external football or bookmaker data. Probability scores and normalization differences do not establish executable odds, calibration, positive EV or profitability.
