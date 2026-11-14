# Real-data provider assessment — research only (2026-11-06)

Related: #452 and draft PR #451. **No data downloaded, ingested, or used to claim positive EV in this assessment.**

## Candidate 1: Football-Data.co.uk
- Official historical CSV overview: https://www.football-data.co.uk/data.php
- Official seasonal downloads: https://www.football-data.co.uk/downloadm.php
- Publishes match results and historical bookmaker odds, with early and closing price columns for some markets/seasons.
- **Licensing blocker:** website states free files are for private individuals, **not commercial or data-training products using automated bots/scrapers/AI**. Obtain explicit written authorization covering intended AI analysis, storage, reuse, and automated ingestion before using this source in the system.
- **Quality blocker:** website warns Pinnacle prices since 2025-07-23 can be systematically out of date. Do not use these as reliable closing benchmarks without independent confirmation.
- **Chronology blocker:** a date and early/closing price column does not by itself prove an exact quote-capture timestamp. Never fabricate captured_at from kickoff, CSV file modification date, or match date.
- **Forecast blocker:** historical odds and outcomes are not the model's independently frozen pre-match predictions. Backtesting an ex-post model on the same data is not OOS evidence.

## Candidate 2: Footiqo
- Official provider referral/details: https://www.football-data.co.uk/footiqo.php
- Paid historical datasets advertised for model development, AI, and backtesting, with opening/closing odds where available.
- **Open questions:** verify exact license terms, allowed redistribution/automation, per-quote timestamps, source coverage, and whether Asian handicap and totals history match our needs before purchase or integration.

## Required next evidence
1. Provider written terms or explicit permission for the intended research/AI workflow.
2. Small licensed sample with actual pre-match capture timestamps, market selection, line, odds, and provider provenance.
3. Independently archived model forecasts generated before the odds snapshot, with training cutoff and model artifact hashes.
4. Independently verified outcomes and a locked chronological evaluation plan.
5. Separate assessment of calibration, realized returns with uncertainty, bookmaker baseline and CLV where available.

## Decision
**HOLD / DISABLED.** Candidate discovery is not a license grant, source verification, live integration, real backtest, or proof of positive EV. Do not download or scrape candidate data under ambiguous terms.
