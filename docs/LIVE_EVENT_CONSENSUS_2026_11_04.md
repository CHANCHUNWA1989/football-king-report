# VNext PR-02: dual-source live event consensus (research only)

**Dependencies:** stacked on PR #429, `ops/point_in_time_store.py`. This is an independent draft research change; no main-branch update, model retraining, paid provider, collection workflow, sportsbook or production recommendation.

## Reproduced gap

The existing `live_score_identity_guard.check` compares match identity, scoreboard and status, but does **not** compare the red-card event set or VAR revision history. Two providers can both report 1–0, while only one has an opposition red card. This should not be trusted as a complete in-play tactical input.

New `ops/live_event_consensus.py` accepts two offline full-feed snapshots with:
- the existing sealed fixture metadata, exact provider event IDs and allowlisted publisher URLs;
- predeclared `source_groups_by_provider` identifying expected upstream families;
- complete goal/red-card event revisions from kickoff, keyed by stable normalized event keys;
- per-revision provider-update and system-receipt timestamps;
- feed update, capture, receipt and available timestamps.

It uses the existing **score identity guard** before event processing, then the PR #429 **point-in-time cut** for all feed snapshots. It returns research-only consensus if event revision history, scoreboard-derived goal counts, red-card counts and VAR status agree. Otherwise it fails closed as `HOLD`. It never silently picks the latest or friendliest provider score.

VAR is represented by revisions of a goal or red-card event: `CONFIRMED -> UNDER_REVIEW -> CONFIRMED/OVERTURNED`. A pending review forces HOLD. A corrected, overturned goal no longer counts in the current score; the earlier event remains as a historical revision. A second yellow leading to a red must be normalized as one `RED_CARD` event, not two. An own goal's `side` must represent the beneficiary team.

## Essential limitations

1. Equal provider strings or `source_group` claims do not prove actual feed independence. The predeclared upstream mapping must be separately authenticated before using events in any forecasting process.
2. Normalized event keys and full-history assertions are only data claims. No independent event-level source verification, VAR federation, referee record, or licensing is performed by this module.
3. An input SHA256 is only an internal deterministic digest; there is **no external wall-clock attestation** or tamper-proof append-only storage here.
4. The module does not authenticate odds, calculate or certify EV, authorize in-play recommendations, or settle match results. Always `model_scoring_eligible=False`, `production_recommendations=DISABLED`.
5. Strict event-key/revision agreement may generate HOLD for two otherwise correct sources with different correction coverage. That is intentional until an independently audited canonical mapping is built.

## Tests and acceptance

New `ops/tests/test_live_event_consensus.py` covers dual-source normal flow, disagreement in red cards and event minute, score mismatch, VAR pending/corrected/revision gap, late receipts, source group conflict, fixture mismatch and score/event reconstruction.

Validation:
```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

Exact-head GitHub Actions, logs and independent review must succeed before merge. PR #429 must also be reviewed and merged first; this branch's checks do not authorize bypassing that dependency. No evidence of improved predictive accuracy, legal live feed availability, usable in-play xG, executable odds or positive EV is claimed.
