# Prospective fixed fixture identity lineage (issue #279)

## Reproduced defect

The 2026-10-20 main run `39368391019` preserved 29 original shadow forecasts, including 27 `openligadb:` event IDs. Its paired cohort contained 20 records but did not retain the original forecast event ID. The archive bridge exported only a legacy league/name/scheduled-time `fixture_id`.

Original decompressed subjects (SHA256, not independent source authentication):

- `forecast_provenance/2026/10/20/39368391019-1/shadow.json.gz`: `eff5e615e02cdc24c785e47db9ee14f97dbbf957c7fe8f86040ba430cbecd742`
- `forecast_provenance/2026/10/20/39368391019-1/paired.json.gz`: `70ba47b235333f575f46bcdb17a6e431b9d0e8cbfdf4b0aeb6a6ef7ff58de510`

New regression tests reproduced missing `forecast_event_id` in both pairing and export before the fix. Signed-case policy tests also reproduced acceptance of an inconsistent populated identity before the fix. Mocked verification stdout in unit tests tests policy boundaries only; actual cryptographic verification must use a fresh CLI invocation on the published run.

## New seals only

`market_pair.py` retains the original `forecast_event_id`. Only the full ASCII pattern `openligadb:[1-9][0-9]*` can yield a typed `source_fixture_identity` containing exactly `provider: OpenLigaDB` and a string `match_id`. Unknown/synthetic event IDs retain their original value without acquiring an OpenLigaDB identity. Invalid types, whitespace, noncanonical IDs and forged populated metadata cannot become a typed provider identity.

`forward_validation.load_archived()` validates populated identity metadata, includes it in equal-timestamp conflicts and quarantines reuse of a provider ID across different fixture keys, including later archived rows. It keeps the existing legacy fixture key. `shadow_archive_bridge.py` preserves already sealed metadata; it does not derive or backfill IDs into older archives.

`forecast_provenance_audit.py` freshly verifies all three signed subjects and additionally requires new paired identity metadata to match the exact original shadow forecast event ID. Legacy subjects without the new metadata keep their existing recorded-time audit semantics. No saved verification JSON substitutes for CLI verification.

Identity preservation remains `UNAUTHENTICATED`, with `independently_verified=false`, `eligible_for_model_scoring=false` and `production_recommendations=DISABLED`. A provider ID is not proof of the market-pair match, publisher identity, upstream independence, actual kickoff or a regulation-time result. No model probability, old seal, result, ledger or qualification threshold is rewritten.

## Recheck

```sh
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
PYTHONPATH=ops python ops/shadow_archive_bridge.py --archives research_pairs --output /tmp/sealed-fixed-identities.json
```

Inspect a newly signed prospective pair and its original shadow subject, then run `ops/forecast_provenance_audit.py` with the exact run/source/workflow SHAs using a current `gh attestation verify` CLI. Matching IDs demonstrate retained lineage only. Export may correctly retain a legacy earliest seal without an ID; a later populated seal must never retrofit that earliest prediction.

## Still required for recommendation qualification

- Immutable, raw-source-linked cross-provider fixture/team mappings, including NDR versus OpenLigaDB.
- Independently authenticated actual kickoff and explicit regulation-time completion/result.
- Applicable publisher/upstream relationships and provenance policy evidence. NDR's `heimspiel_shorthand_…` technical external IDs and general result-service navigation links do not establish feed independence or licensing.
- Sufficient genuinely prospective, independently settled same-cohort A/B/C/market comparisons, calibration and uncertainty showing an advantage. Existing 300-match/12-week/league gates remain unchanged; the separate four-model experiment also retains its original minimum.

Until these are met the system remains HOLD/DISABLED; engineering tests do not establish better predictions.
