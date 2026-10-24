# Historical odds source decision — 2026-10-24

## Football-Data.co.uk — RESTRICTED FOR AI PIPELINE

Official source: https://www.football-data.co.uk/data

The site's official Data page explicitly states that free files are intended for private individuals, **not commercial or data-training products using automated bots/scrapers/AI**. Therefore do not assume that the repository's AI training/backtesting pipeline is permitted to automatically retrieve, ingest or redistribute the site's CSV data. This restriction supersedes the earlier unverified candidate assessment.

- Automated download, scraping, bulk ingestion, AI training and redistribution: BLOCKED unless explicit permission for the specific use is obtained.
- Manual personal analysis may be a different use case, but is not a blanket authorization for this repository's automated AI workflow.
- No provider key, paid API or extra credits authorized.
- CSV header and settlement code remain generic, source-agnostic, offline tooling only.
- No real historical Football-Data rows have been imported; no ROI, EV, model out-of-sample performance or live quotes have been established.
- Historical opening and closing prices must be treated separately; closing odds are not available at earlier prediction timestamps.

## Next permitted actions

1. Seek an alternative genuinely open dataset with an explicit license permitting the intended AI evaluation and automated use; record license URL, attribution, scope and version.
2. Alternatively obtain written permission from the rights holder before integrating this source.
3. Use local synthetic fixtures only to test schema/settlement code while permissions are unresolved.
4. When a compliant dataset is obtained, run the fixture-integrity audit and O/U 2.5 market baseline, then time-ordered model evaluation.

Decision: SOURCE_NOT_APPROVED_FOR_AUTOMATED_AI_USE; totals/spreads HOLD; production recommendations DISABLED.

## Alternative source screening — 2026-10-24
- openfootball/football.json and footballcsv: public-domain / CC0 match results candidates, useful for outcomes and fixture integrity; do NOT provide verified historical bookmaker totals/spreads quotes. Primary source: https://openfootball.github.io/ ; directory: https://github.com/withqwerty/open-football
- martj42/international_results: CC0-1.0 men's international match results; repository https://github.com/martj42/international_results ; no verified bookmaker odds. Distinguish international matches and possible extra-time scoring from league full-time settlement.
- xgabora/Club-Football-Match-Data-2000-2025 declares MIT but states match results and odds derive from Football-Data.co.uk; upstream restrictions unresolved, so DO NOT ingest betting odds on downstream MIT label alone.
- datasets/football-datasets similarly says league data are derived from Football-Data.co.uk despite downstream public-domain declaration. Do not treat downstream relicensing as upstream rights clearance.
- Decision: CC0 match-results datasets are candidates for score-only settlement and prediction research after direct license/provenance check; NO APPROVED FREE HISTORICAL ODDS DATASET YET. Never fabricate market ROI without quote provenance.
