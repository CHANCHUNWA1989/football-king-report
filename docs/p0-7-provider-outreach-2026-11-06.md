# P0-7: Provider permission outreach and zero-cost evidence gate (2026-11-06)

**Scope:** Draft PR #451, Issue #452, research only. These are **unsent drafts**, not licenses, agreements, purchases, authenticated API tests or confirmed bookmaker timestamps. Preserve `PRODUCTION_RECOMMENDATIONS=DISABLED` and `POSITIVE_EV_VERIFIED=False`; no public picks, deployment or auto-betting.

## What was verified from public pages (not authenticated API samples)

- **TheStatsAPI**: https://www.thestatsapi.com/odds-api lists bookmaker odds, Asian handicaps, totals, and opening/closing pricing. Contact: https://www.thestatsapi.com/contact . This does **not** establish that past per-quote publication/update/capture UTC timestamps exist or that the desired historical storage/model use is licensed.
- **Footiqo**: https://footiqo.com/premium/premium-football-database/ describes historical data, some opening/closing odds, and private ML research uses; says automated website scraping/crawling needs advance written permission, and says **no public API currently**. Contact: support@footiqo.com. Do not assume its datasets contain complete timestamped Asian handicap and goals totals history.
- Product descriptions/prices, FAQ rate limits and plan-specific rights may differ or change: request a current **written contract/scope** before spending. No data downloaded.

## Unsent draft 1 — TheStatsAPI

**To:** Use the official https://www.thestatsapi.com/contact form (verify reply address before sending).  
**Subject:** Research data licence and timestamped Asian odds sample — Football King V

Hello TheStatsAPI team,

We are evaluating a football analytics research system, Football King V. Before subscribing, could you confirm in writing whether a suitable plan permits private automated analysis, ML training and backtesting, storage of original payloads and SHA-256 integrity evidence, and the intended retention period? Please distinguish private use from publication of model-derived recommendations and redistribution of raw odds.

We need historical and prospective **pre-match** bookmaker quotes for 1X2, Asian handicap (including quarter-goal lines) and over/under goals, ideally covering multiple bookmakers. A small representative, non-sensitive **sample JSON/schema** would help us verify:
- stable match, team, bookmaker, market, selection and line IDs;
- decimal odds, actual per-quote bookmaker update time, provider snapshot time, and source-capture/receipt time in UTC;
- whether those timestamps are historically available as point-in-time snapshots, rather than only opening/closing labels;
- event kick-off changes, line revisions, withdrawn/void prices, and availability/executable-price limitations;
- match result/status and mapping to independent outcome sources.

Please also confirm exact historical coverage per market/league/season, API endpoints, rate limits, trial/sample options, commercial/AI usage terms, data retention/republication restrictions and the applicable price. We do not request API keys or any billable access at this stage.

Thank you.

Football King V research team

## Unsent draft 2 — Footiqo

**To:** support@footiqo.com  
**Subject:** Historical Asian handicap and totals data: fields, sample and research licence

Hello Footiqo team,

We are assessing historical football datasets for private ML/backtesting research in Football King V. Your site describes downloadable research datasets and notes that a public API is not currently offered. Before purchasing, could you confirm whether a downloadable or custom dataset includes **Asian handicap and goals over/under** odds at exact quarter-goal lines, with multiple bookmakers and stable event IDs?

Most importantly, for each historical price, do you provide an authentic UTC bookmaker update or independently observed capture timestamp, rather than just an opening/closing label? Could you share a small permitted, non-sensitive schema/sample showing the event ID, UTC kickoff, bookmaker ID, market/selection, exact line, decimal odds, timestamp and correction/void status?

Please confirm which leagues/seasons/markets are covered, the source and reliability of timestamps, whether model training/backtesting plus private storage and retained raw records are licensed, restrictions on redistribution or published derived recommendations, custom collection options, and any cost or trial data. We will not scrape or automatically extract material without written permission.

Thank you.

Football King V research team

## Decision checklist — all answers must be source-backed

| Gate | Required from vendor or separately from owner | Current status |
|---|---|---|
| LICENSE | Written rights for automated ingestion, AI training, private storage/retention and intended display | WAITING_PROVIDER |
| MARKET | Real bookmaker ID, event and selection ID, exact AH/total line, original decimal price | WAITING_PROVIDER |
| TIME | **Authentic** per-quote update/snapshot/receipt UTC, point-in-time history, not inferred timestamps | WAITING_PROVIDER |
| COVERAGE | Market/season/bookmaker coverage, corrections, voids, rate limits, data availability | WAITING_PROVIDER |
| FORECAST | Owner's independent pre-kickoff sealed model/forecast, SHA, run ID and training/outcome cutoff | BLOCKED_EXTERNAL |
| RESULT | Independently verified FT90 event ID bridge, final score/status and timestamp | BLOCKED_EXTERNAL |
| SECURITY | Issue #439 branch protection and independent human review | OWNER_ACTION_REQUIRED |

**Pass rule:** A provider marketing page or API schema alone is not a licence and is not actual data receipt. A single properly authorised example can test the adapter; it cannot establish model edge, ROI or verified positive EV. Do not backfill previously unrecorded forecasts.

## Minimal-cost next step and Codex tool policy

1. **Owner action**: review and send the two drafts using verified provider contacts if desired; this file does not send them. Never place secrets, paid/raw bookmaker payloads or personal billing data in public GitHub or chat.
2. **Codex default**: a single coordinator/implementer; `git`, `rg`, existing `ops/` scripts and GitHub Actions first. Check the actual MCP configuration with `codex mcp list` or Codex `/mcp` before claiming any external tool was used.
3. **Read-only MCP on demand**: Context7 for unfamiliar library APIs; public OpenAI docs MCP for OpenAI/Codex API facts; GitHub MCP only when its PR/issue capabilities add value beyond `git` and `gh`. Do not install a server just to answer a settled task.
4. **Firecrawl or browser**: only when a *new* external factual question or vendor response makes it necessary, and after checking credits and terms. A search or scrape can itself consume provider credits and model tokens; it is not a guaranteed Codex-quota saving.
5. **MagicPath / Health / Outlook / Documents / Spreadsheets**: not needed for this data-rights gate. Keep external accounts and private data out of the coding-agent context.
6. **Next state**: `WAITING_PROVIDER`, `OWNER_ACTION_REQUIRED`, `HOLD/DISABLED`. Return only on new written vendor rights, authorised raw sample, genuine sealed forecast/result inputs or security approval. No CI rerun needed for this documentation-only change; independently confirm exact-head CI before any later release consideration.

## Links
- [Issue #452](https://github.com/CHANCHUNWA1989/football-king-report/issues/452) — data provenance blocker.
- [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439) — security/human release blocker.
- [Existing provider assessment](provider-decision-memo-2026-11-06.md) and [capture contract](p0-1-market-capture.md).
