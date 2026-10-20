# Raw fixed-ID replay against freshly verified forecast subjects (#283)

## The missing connection

PR #280 retains the original forecast event ID and strictly typed prospective OpenLigaDB identity. The existing raw FT parser omits `matchID` and both `teamId` fields, so a name/date match cannot establish the original provider identity. This change adds a separate raw replay path and leaves the old parser, original forecasts, results and scoring logic unchanged.

A retained native input (`39371240014`, 2026-10-20) contains 306 OpenLigaDB raw rows, including 54 publisher-marked finished rows. Raw SHA256 `280f2e8d7383fda61167224bfe2a9098f71f6f01a9984313cc0611560b7a01c3`, 308338 bytes. These counts/digests describe unverified input only; they do not certify any outcome. The 20-pair signed prospective snapshot has 18 canonical OpenLigaDB identities and two synthetic IDs. Legacy identities are never backfilled.

## Reproducible input/output

1. `ops/prepare_forecast_proof.py` selects the highest numeric `(run_id, attempt)` among existing permanent forecast archive directories. This is the latest **available archived snapshot**, not a claim of the newest GitHub run or newest source data. If the selected archive is malformed or incomplete, preparation fails visibly without an older fallback.
2. The preparer queries the official attempt-specific GitHub run API and requires the exact repository identity, main branch, completed successful workflow path, run/attempt and source SHA. It copies only four bounded original gzip subjects/bundle into a fresh directory. It neither reads nor copies saved verification reports. Preparation is not signature verification.
3. `ops/raw_openligadb_identity_linkage.py` invokes `forecast_provenance_audit.audit()` in the same process and requires its fresh CLI verification of all three original subjects, exact expected run/source/workflow identity and recorded-time audit. It rereads the paired bytes and requires their digest to match this invocation's audit before using IDs. Saved `*.verification.json` or audit JSON cannot substitute for a fresh verification.
4. The linker reads the fixed OpenLigaDB raw file and manifest, verifies bounded byte size, digest, schema, source URL/path and explicit UTC, and parses the same checked bytes with duplicate JSON keys and nonfinite numbers rejected. Strict positive integer match/team IDs become canonical strings. Repeated raw IDs, conflicting seals, malformed IDs/times or exact-ID team/kickoff conflicts are isolated; names/dates are never fallback keys.
5. An exact scheduled ID link does not create an outcome. A publisher-marked finished result needs `matchIsFinished is True`, one strict integer `resultTypeID == 2`, strict goal integers and internally consistent claimed chronology to become an **unauthenticated FT candidate**. Only exactly linked candidates count. None qualify for model scoring.

The daily workflow reuses its existing raw download; this feature adds no sports API requests. It saves proof selection and fixed-ID replay reports as separate artifacts, without feeding them into FT/scoring/readiness eligibility. `actions: read` is the only additional GitHub permission.

```sh
python ops/prepare_forecast_proof.py --archives forecast_provenance --output-dir /tmp/new-forecast-proof
python ops/raw_openligadb_identity_linkage.py \
  --raw-dir /path/to/raw_sources --proof /tmp/new-forecast-proof \
  --source-sha EXACT_RUN_SHA --workflow-sha EXACT_WORKFLOW_SHA \
  --run-id EXACT_RUN --attempt EXACT_ATTEMPT --output /tmp/raw-id-linkage.json
python -m compileall -q ops
python -m unittest discover -s ops/tests -q
```

Use the actual values returned by preparation. The source/workflow equality assumption is checked by the actual verifier; a different signer digest fails closed. The runtime's older `gh` cannot verify attestation; genuine cryptographic acceptance is established only by this round's fresh hosted CLI execution. Mocked test stdout tests boundaries, not cryptographic validity.

## Trust boundaries and remaining work

`forecast_signature_reverified` concerns the forecast bytes and workflow identity only. The raw collector's v1 manifest has no authenticated origin/capture chain. Recomputing a raw hash cannot authenticate a publisher response, independence, capture time or data freshness. Raw team IDs remain observations, because the sealed forecast does not authenticate those team IDs.

Every result remains HOLD/DISABLED, independently_verified=false, eligible_for_model_scoring=false and eligible_for_betting_promotion=false. Actual kickoff and regulation-time FT authentication remain false. A same-provider fixed ID is not a cross-provider fixture mapping or an independent result. NDR's technical external ID and two publisher names cannot change that policy.

Still needed: authenticated raw origin/time chains, independently supported fixture/team mappings, actual kickoff and regulation-period result evidence, publisher/upstream independence, sufficient genuinely prospective same-cohort samples and calibrated advantage over market. No old seal/probability/result/ledger, model weights or qualification thresholds change. There is no evidence of prediction improvement from this engineering change.
