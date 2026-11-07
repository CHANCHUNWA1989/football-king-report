# Scoped penaltyblog reuse

- Upstream: https://github.com/martineastwood/penaltyblog
- Pinned commit: `6870f0e762e9cba35fa722dc14a8daeaf8bc6134`
- Algorithm reference: `penaltyblog/metrics/metrics.pyx` (`compute_rps_array`) and `penaltyblog/metrics/rps.py`.
- Licence: MIT, Copyright 2021 Martin Eastwood; permission text retained in `LICENCE`.
- Adapted location: `ops/market_shrinkage.py:ranked_probability_score`.

The cumulative-forecast versus cumulative-outcome squared-error algorithm is adapted to a standard-library-only scalar 1X2 function, fixed home/draw/away ordering, and the existing strict numeric/outcome validation. Accepted probability-sum rounding residuals are normalized locally; score normalization is number of classes minus one. Existing shrinkage and daily reports reuse this same function; paired model/market evidence now exposes descriptive RPS on the same settled cases.

No NumPy/Cython dependency, scraper, live API, model, dataset or third-party performance claim is copied. MIT software permission does not grant rights to any external football or bookmaker data. RPS is a probability score and does not establish executable odds, positive EV or profitability.
