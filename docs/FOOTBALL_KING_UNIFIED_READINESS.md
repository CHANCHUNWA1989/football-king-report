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
