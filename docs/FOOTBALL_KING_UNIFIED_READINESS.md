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
