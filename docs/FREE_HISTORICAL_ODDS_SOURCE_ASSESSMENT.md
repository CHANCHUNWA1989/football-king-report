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
