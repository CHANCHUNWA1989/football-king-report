# Codex low-cost handoff

- Branch/PR: research/issue-450-asian-settlement / Draft #451
- Last plan commit: 7396ccde24b7f1aaabe8a6cf285a1818a1202473
- Last verified CI: cb34d5903a68fa9453dac96a82e1180b2910d8a1 — six workflows successful; newer commits not yet verified
- Current phase: 0 — inspect actual market/latest.json schema and focused existing market-consensus audit tests; do not presume a defect
- Existing modules: ops/forward_validation.py, ops/market_pair.py, ops/prematch_evidence_capture.py, ops/the_odds_api_adapter.py, ops/frozen_forecast_join.py
- Evidence blockers: 77 unverified settled 1X2 rows; no verified executable Asian quotes, no independent outcome attestations; market consensus is not executable odds
- Next single action: compare ops/audit_existing_market_consensus.py assumptions with actual market/latest.json structure, then add/fix tests only if a real mismatch is reproduced
- Safety: research-only HOLD/DISABLED; no merge, deploy, paid API or automatic betting
