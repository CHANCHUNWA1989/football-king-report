# Provider decision memo — 2026-11-06

Related to issue #452, draft PR #451. Research only; no data downloaded, API connected, subscription purchased or betting enabled.

## Verified official pages

1. Football-Data official use policy: https://football-data.co.uk/contact.php
   - Free CSVs are intended for private individuals and academic interest; the site states commercial/AI/model-training requests using automated scraping should assume permission is not granted. At most light twice-weekly automated downloads for permitted personal use.
   - **Decision: do not programmatically ingest into this AI system without explicit permission.**
2. Football-Data historical odds page: https://football-data.co.uk/data
   - Includes Asian handicap and totals in some seasons. Opening and closing columns are not necessarily independently timestamped per quote.
   - Site warns Pinnacle quotes since 2025-07-23 may be systematically stale.
3. TheStatsAPI provider introduction: https://football-data.co.uk/thestatsapi.php
   - Advertises historical/current/opening/closing 1X2, totals and Asian handicap odds and commercial application use; entry subscription advertised from GBP 39/month.
   - **Decision: priority for vendor evaluation only.** Check contract, endpoint response fields, historical depth, capture timestamps, rate limits, permitted storage and AI training before connection.
4. Footiqo data overview: https://football-data.co.uk/footiqo.php
   - Advertises historical AI/backtest datasets from 2015/16 with opening/closing odds where available.
   - **Decision: secondary candidate.** Need quote timestamp granularity and handicap/totals market coverage verified.

## Vendor acceptance checklist
- [ ] Explicit permission to store and use data in automated AI/model research.
- [ ] Actual per-quote capture timestamps in UTC, not merely opening/closing labels.
- [ ] Historical Asian handicap and totals selection/line/decimal odds, bookmaker ID and event ID.
- [ ] Point-in-time availability and late corrections policy.
- [ ] Provider-signed sample schema / sample payload without secret keys.
- [ ] Match outcomes, cancellation/void rules and event-ID reconciliation.
- [ ] Rate limits, costs, redistribution and retention rights.
- [ ] Frozen pre-match model forecasts and model training cutoff from our own logs, independent of odds vendor.
- [ ] Independent reviewer signoff; SHA-256 dataset manifest and chronological holdout plan.

## Explicit blockers
A vendor's advertised commercial use does not prove that the chosen plan licenses every intended AI training use. Opening/closing odds alone cannot establish a quote-capture timestamp. A vendor feed cannot reconstruct a forecast that the model did not save before kickoff.

**Gate: HOLD / DISABLED. No verified positive EV, no real-data OOS claim.**
