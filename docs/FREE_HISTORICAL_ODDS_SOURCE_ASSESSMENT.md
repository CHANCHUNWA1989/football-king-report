# Free historical odds source assessment — 2026-10-24

## Candidate: Football-Data.co.uk

- Public source: https://www.football-data.co.uk/downloadm.php
- Publicly advertises downloadable historical CSV/Excel results, total-goals odds and Asian-handicap odds.
- Documents opening and closing odds series since 2019/20; opening odds and closing odds MUST NOT be mixed as contemporaneous quotes.
- Candidate use: offline, time-ordered backtesting and settlement verification; NOT a live executable sportsbook quote.
- License/automated redistribution and bulk-download permission: UNVERIFIED. Obtain explicit terms/permission before automating collection or redistribution.
- Fixture mapping: league, match date, home team, away team; require collision and timezone review.
- CSV columns: inspect the source Notes.txt and headers before mapping. Do not assume all seasons have identical fields.
- Data lineage: source URL, retrieval timestamp, source season, row identifier, bookmaker, opening/closing designation, odds line and result.
- Leakage rule: closing prices cannot be treated as known at earlier prediction timestamps.
- Zero-cost guard: no paid endpoint, subscription, API key or provider-credit consumption.
- Status: SOURCE_CANDIDATE_ONLY. Both totals and spreads remain HOLD; production recommendations DISABLED.

## Acceptance steps

1. Verify use/automation terms and inspect a single published CSV schema.
2. Create a fixture-backed offline importer and map O/U + Asian-handicap columns, with explicit missing-column handling.
3. Validate settlement including whole, half and quarter-goal lines.
4. Run chronological out-of-sample tests, calibration and benchmark comparisons.
5. Review CI and evidence before enabling research reporting. Do not enable production betting recommendations.
