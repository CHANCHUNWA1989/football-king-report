# Football King — Unified Readiness Gate (2026-10-24)

## Purpose
Single, evidence-based release plan for the football research system. A passing CI run is **not** proof of positive betting EV. Keep all betting recommendations DISABLED until the gates below are met.

## Verified baseline
- Market archive: 2026-10-24T04:18:14Z; 103 events; RESEARCH_ONLY; 1X2 no-vig bookmaker consensus.
- Snapshot quota: 322 used / 178 remaining at archive time; **not a live quota balance**.
- Missing verified markets: spreads (Asian handicap), totals (over/under).
- Production recommendations: DISABLED; executable sportsbook odds and positive EV unverified.
- Development branch: fix/live-data-freshness-20261023; PR #308 is the review entry point.
- Prior CI evidence: six workflows completed successfully on commit 3b919d83201397da7b8815462d3c11e84f27dae7; **newer commits need their own checks**.

## Gate A — Data integrity (required)
- Run `python -m unittest -v ops.tests.test_market_health_audit` on the latest branch commit.
- Verify quote age against inspection time, capture/quote chronology, kickoff in the future, market coverage and quota guard.
- Validate full market archive against `ops/market_archive_guard.py`; reject malformed records.
- Verify collection status corresponds to the same capture timestamp.
- Zero new provider API calls for offline tests.

## Gate B — Market coverage (required)
- Confirm legitimate, permitted and cost-controlled source for 1X2, Asian handicap and totals.
- Store provider evidence, timestamp, league/event mapping and market availability.
- Never relabel derived 1X2 consensus as bookmaker-executable odds.
- Missing markets must remain HOLD.

## Gate C — Out-of-sample model validation (required)
- Time-ordered train/validation/test split, no look-ahead or outcome leakage.
- Report by league and market: sample sizes, Brier/log loss, calibration, coverage, baseline comparison, uncertainty.
- Freeze model and evaluate genuinely unseen matches before any promotion.

## Gate D — Paper-trading evidence (required)
- Record timestamped executable quotes, market line, model probability, implied probability, edge, closing line, result and costs.
- Audit stale odds, void rules, missing prices and settlement errors.
- Report ROI, yield, drawdown, CLV and confidence intervals; no guarantee of profitability.

## Release decision
- Current: **HOLD / RESEARCH_ONLY**.
- Do not merge or enable betting outputs solely because CI is green.
- Next engineering action: run/inspect latest branch CI, then prioritize verified totals/spreads source integration without violating API quotas.

## User decision only when required
Request explicit approval only for new paid data subscriptions, additional secrets/permissions, or a production rollout. Routine code changes, offline tests and evidence reviews can proceed without repeated user actions.

## Free-only market policy (confirmed 2026-10-24)
- User authorized free data only; no subscriptions, paid endpoints or additional provider credits for this update.
- Existing archive stores h2h consensus only. Spreads and totals remain HOLD until independently verified free data and schema exist.
- Do not infer handicap or total probabilities from h2h consensus or treat derived probabilities as executable quotes.
- First validate source terms, timestamps, event IDs, settlement rules and market-line structure offline.
- Latest CI on prior unified-readiness commit 0288e1abe939521028b8a248349e7c9b3cbec79f: 6/6 completed successfully. New commits require independent CI verification.

## Consolidated update — 2026-10-24
- Previous commit ea2822dbd3dcb6d97cf421c825d487850ba60e5d: six GitHub CI workflows completed successfully.
- The health audit now reports separate h2h, spreads and totals readiness; only h2h can be RESEARCH_ONLY from the current schema. Spreads and totals remain HOLD.
- 1X2 readiness now requires an explicit requested_markets declaration containing h2h; absent declaration is UNVERIFIED_1X2_SOURCE and HOLD.
- Regression tests added for per-market readiness, quote/capture chronology, and missing h2h source declaration.
- No provider API call, subscription, or paid data source was initiated by these code changes.
- Latest commits after ea2822d still require their own completed CI verification; no production deployment authorized.

## Next execution order
1. Confirm six workflows for latest commit fc720873d8ce342b0c249b4a5459acf0928f4e50.
2. Audit permitted free sources for totals/spreads and map explicit market lines, outcomes and timestamps without downloading paid odds.
3. Add offline fixture tests for any validated source; preserve HOLD for unverified markets.
4. Once a time-ordered dataset exists, measure baseline-relative calibration and out-of-sample accuracy before paper trading.

## Consolidated verification — 2026-10-24 (latest)
- Commit 8e1b3672c6f0e5b33529c4b1ef205f84c5eb7bae: all six GitHub Actions workflows completed successfully.
- The cached market health audit now rejects malformed or duplicated requested_markets metadata; h2h requires explicit provenance. Totals/spreads remain HOLD under current 1X2-only archive schema.
- A regression test checks malformed market declarations. New commits need independent CI verification.
- No extra provider call or paid subscription authorized. No change to production_recommendations=DISABLED.
- Next milestone: identify a license-compatible zero-cost totals source with explicit line, Over/Under outcome, timestamp and fixture ID; only then implement an offline adapter and test fixtures. Repeat separately for Asian handicap with line and settlement rules.

## Free totals/spreads offline schema milestone — 2026-10-24
- CI on prior commit 483f7b63bb25d3bcdf9943fe8449e4105ba642ca: 6/6 workflows successful.
- Added ops/free_market_quote_schema.py and ops/tests/test_free_market_quote_schema.py for zero-network quote validation.
- Validation covers fixture ID, source identifier, market type, quarter-goal line, exact two-sided outcomes, decimal prices, quote timestamp and future kickoff.
- SCHEMA_VALID_ONLY does not mean a source is licensed, live, executable, complete or profitable; no provider is connected by this module.
- Next: verify CI on the new code; review permitted free provider source and mapping before integration.

## Current consolidation: offline quote timing safety
- Verified previous consolidated commit 483f7b63bb25d3bcdf9943fe8449e4105ba642ca had six successful CI workflows.
- Free totals/spreads offline quote schema now rejects kickoff within 10 minutes of capture, consistent with pre-match-only collection policy.
- Added tests for too-close kickoff and quotes timestamped after capture.
- This is **not** a live totals/spreads feed; market status stays HOLD and production recommendations DISABLED.
- Next acceptance gate: six green workflows for latest commit, then provider licensing and genuine free-market availability evidence. No API spending authorized.

## Consolidated status — 2026-10-24 (CI-confirmed)
- Prior consolidated commit 8e180823e35711221134285d72f0a77cd6a64a30: 6/6 GitHub Actions succeeded.
- Added an explicit quote-before-kickoff check and regression test for totals/spreads offline schema.
- The offline schema is NOT proof of any free live source, license rights, actual odds execution or positive EV.
- Release remains HOLD / RESEARCH_ONLY. Next steps: verify new CI; obtain zero-cost licensed source evidence; then fixture mapping, line/settlement tests and time-ordered paper evaluation.

## CI incident and repair — 2026-10-24
- Commit df427a9cf361b5a5c4360cd2a79a3c7935af1a5f: 4 successful and 2 failed workflows. Both failures came from one assertion in test_quote_timestamp_at_kickoff_is_rejected.
- Root cause: future-to-capture check raised STALE_OR_FUTURE_QUOTE before quote-at-kickoff check could raise QUOTE_AT_OR_AFTER_KICKOFF. Both rejected unsafe data; ordering contradicted the asserted reason.
- Fix commit 9c4c66e97a2803b097e6df70eefdd9bf64683446 prioritizes the more specific kickoff error. Must verify CI on the new head; do not assume green.
- No live totals/spreads provider is connected; both remain HOLD. No paid service or extra API request initiated.

## Batch market intake milestone — 2026-10-24
- Verified previous head 9e3bf7897ba10a01a1e0b0ebf7805e086fcca834: 6/6 GitHub workflows successful after CI regression repair.
- Added ops/free_market_batch_gate.py and offline tests to reject empty, malformed or duplicate source/fixture/market/line batches atomically.
- Valid batches remain SCHEMA_VALID_ONLY, never production-ready. No real totals/spreads source has been integrated.
- Next: verify CI for latest batch code; identify and document a genuinely free licensed provider, fixture mapping and actual quotes before any connector work.

## Free historical data source discovery — 2026-10-24
- Commit 6dbbf4bfa4cc00e86665aa8c1a22a9252e5e3936: six GitHub Actions workflows completed successfully.
- Identified Football-Data.co.uk historical CSV archive as a zero-cost *candidate* for totals and Asian handicap offline research; source review in docs/FREE_HISTORICAL_ODDS_SOURCE_ASSESSMENT.md.
- Permission for automated retrieval and redistribution remains UNVERIFIED; do not scrape or auto-download pending review. This is not a live odds feed.
- Next engineering task: inspect public Notes.txt and CSV headers, then implement a no-network fixture-backed parser and settlement tests. Keep spreads/totals HOLD and production DISABLED.

## Historical CSV offline intake — 2026-10-24
- Verified previous commit 034fa2152ff066d448c8f9d501d7ab1b295cf8a3: 6/6 workflows successful.
- Added ops/historical_odds_header_audit.py and tests to inspect CSV headers without downloading any data or spending provider credits.
- Candidate field names are hypotheses pending actual source Notes.txt/header inspection; no historical CSV was ingested and no backtest has been run.
- Next: confirm source terms and actual file schema, then map explicit opening vs closing quote timing, fixture identifiers, settlement rules and time-ordered test splits.
- Totals/spreads HOLD; production recommendations DISABLED.

## Offline totals 2.5 settlement milestone — 2026-10-24
- Prior commit 9321bda9d6f901e6812acd6671b429b19f2b2e76: 6/6 workflows successful.
- Added ops/historical_total_2_5_settlement.py and tests for full-time Over/Under 2.5 settlement and flat-stake unit P/L.
- This is settlement logic only; no actual CSV rows, predictive probabilities, chronological backtest or ROI evidence were produced.
- Next: verify CI; confirm source terms and actual historical CSV columns, then implement a reproducible offline loader and pre-specified out-of-sample evaluation.
- Production recommendations DISABLED; totals/spreads remain HOLD.
