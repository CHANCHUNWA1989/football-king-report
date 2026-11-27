# Point-in-time evidence cut | 2026-11-04

## Scope

Independent **offline research-only** sidecar:
- `ops/point_in_time_store.py` provides `build_cut`, `audit_cut`, and `verify_pinned_cut`.
- `ops/tests/test_point_in_time_store.py` covers 18 synthetic unittest cases.
- No production pipeline, scheduled collection, historical A/B/C model, sealed forecast, odds feed, dashboard, key, or betting function has been modified.
- All returned objects preserve `production_recommendations = "DISABLED"`; failure is `HOLD`. A passing temporal gate returns `RESEARCH_ONLY` **not** verified source evidence or authorization to bet.

## Problem reproduced

A model decision **at Hong Kong time 04:49** can accidentally consume an event that happened at 04:44 but was **received at 04:52**. The latter event is not a valid feature for the earlier decision, even though its match event time is older.

The synthetic regression `test_late_received_goal_rejected_despite_old_upstream_time` rejects this case. Additional tests cover late xG, wrong fixture, out-of-order timestamps, duplicate IDs, missing clocks, undeclared result/verification claims, offset normalization and digest tampering.

## Contract

Each evidence row has:
- immutable identity fields: `evidence_id`, `fixture_id`, `kind`, `source`, `source_group`, `source_event_id`;
- `source_updated_utc` (provider's claim), `captured_utc`, `received_utc`, `available_utc`;
- `raw_sha256` as a caller-supplied lowercase SHA256 string. **Its content has not been independently verified by this module.**

The module enforces `source_updated_utc <= captured_utc <= received_utc <= available_utc <= decision_utc`, correct canonical fixture identity and pre-match/in-play phase order. One contaminated evidence row fails the entire cut; no silent selection of the favorable subset. Input metadata is normalized to UTC and sorted by evidence ID, then SHA256-hashed deterministically.

`input_sha256` detects alteration **only when compared against a trusted, separately pinned anchor**. Rewriting every record and its digest is not prevented by a self-contained hash. This module does **not** provide a tamper-proof physical store, cryptographic signatures, independent wall-clock attestation, verified publisher rights, licensed sportsbook quotes, or model calibration.

## Integration boundaries

A future reviewed PR may pass a properly pinned cut to the **research** shadow model before generation; it must check separately:
1. source identity and source independence (the `source_group` text is a claim, not authentication);
2. freshness, events, red cards and upstream correction reconciliation;
3. executable-quote rights and timing, where applicable;
4. independent archival anchoring of the decision receipt;
5. forward-only and cross-validation protections.

The existing guards `live_score_identity_guard.py`, `live_recommendation_guard.py`, `live_quote_snapshot_guard.py` and `forecast_decision_journal.py` remain authoritative for their respective scopes. This module does not replace or bypass them.

## Validation commands

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

A local isolated copy of the new module and test file passed **18 synthetic unit tests** and compilation. Full-repository GitHub Actions and independent review must be checked against the **exact PR commit SHA** before considering merge. No claim of live data access, forecast accuracy gain, EV, CLV, ROI or production readiness.
