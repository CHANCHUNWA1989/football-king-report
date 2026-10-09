# Forward settlement research audit (2026-10-09)

Run: `python ops/forward_settlement_audit.py --input forward_records.json --output forward-settlement-audit.json`.

Input: JSON list of records with `event_id`, `model_version`, `market`, `prediction_created_at_utc`, `source_snapshot_at_utc`, `kickoff_utc`, `settled_at_utc`, `immutable_prediction_record`, `independent_settlement_verified`, `historical_backfill`, `predicted_probability`, `settled_binary_outcome` (0/1), `market_baseline_probability`.

This is an **offline diagnostic only**. Flags such as `immutable_prediction_record` and `independent_settlement_verified` are **self-attested input**, not independently authenticated by this tool. Counts are candidate samples, not certified forward evidence. The module checks time order, rejects backfills/duplicates, calculates model and market-baseline Brier scores, but does not independently fetch results, inspect signed prediction logs, calculate uncertainty or validate calibration. A separate independently authenticated settlement provenance system and statistical review are required. **Do not promote models or publish betting picks from this output.**

The current repository has no proven independently settled forward sample set. Never populate records with synthetic fixtures and call them production evidence.
