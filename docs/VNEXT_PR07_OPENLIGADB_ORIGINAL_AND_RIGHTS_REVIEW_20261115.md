# VNext PR-07 — First real OpenLigaDB historical original and source-rights review

**Research observation: 2026-11-15 07:50:50 UTC.** This is an actual
**read of the provider's HTTPS result API**, and a real-byte checksum
demonstration. **It does not verify an independently attested publisher,
a signed capture timestamp, an independent second result source, an
archived pre-kickoff forecast, an actual official final result, or a
certified prospective OOS match. Keep HOLD / DISABLED.**

## 1. Material improvement: newly verified source terms

Directly checked the original **German** provider pages, both marked
updated **07.11.2026** (the English translations are non-authoritative):

- [OpenLigaDB data license](https://www.openligadb.de/lizenz):
  provider states sports data is under **ODbL 1.0**, allowing free use,
  copying, modification and commercial use under the stated license
  obligations. Public display requires prominent **OpenLigaDB
  attribution**; redistribution of a modified *database* may trigger
  share-alike obligations and may not impose additional technical
  restrictions. Club logos, crests and external images are not included.
- [OpenLigaDB API terms](https://www.openligadb.de/nutzungsbedingungen):
  API use is separate from the data license. The provider requests
  restrained polling, caching, a meaningful application User-Agent,
  a backoff response to HTTP 429/5xx and no excessive load.
  No keys/registration are currently required per these published terms.
- The provider expressly says match results are
  **community-submitted without editorial fact checking**, and
  **has no publicly accessible change history or immutable historical
  snapshots**. The claim that contributor-entered data are not imported
  from third-party databases is a **publisher statement, not independent
  proof of its upstream collection independence for any specific fixture**.

**Licensing decision:** these new official documents support a
source-specific permission review for OpenLigaDB data under ODbL 1.0.
They do **not** establish full legal compliance for the future VNext
deployment, independently authenticated upstream match data,
captured-before-kickoff prediction evidence, or independent corroboration
with NDR/DFB. Do not silently override the current pinned
`ops/policies/result_sources_v1.json` policy that holds
`REQUIRES_SCOPE_SPECIFIC_LICENSE_REVIEW` and
`upstream_relationship=UNKNOWN`. Independent review is still required.

## 2. Actually received one real provider 90-minute result JSON

A disposable isolated Python 3.11 Linux research sandbox made **one**
GET request on 2026-11-15 to:

`https://api.openligadb.de/getmatchdata/83156`

The request used a transparent GitHub-repo User-Agent
`FootballKingVNext-Research/0.1 (+https://github.com/CHANCHUNWA1989/football-king-report)`.

Observed at HTTP response:

| Check | Observed |
| --- | --- |
| HTTP status | **200** |
| Returned request URL | `https://api.openligadb.de/getmatchdata/83156` |
| HTTP Content-Type | `application/json; charset=utf-8` |
| HTTP Date (not independently signed) | `Sun, 15 Nov 2026 07:50:50 GMT` |
| Sandbox local receive time (not independently signed) | `2026-11-15T07:50:50.323115+00:00` |
| Actual response size | **2,508 bytes** |
| Actual bytes SHA-256 | `420aca223bdc71d3a5f88a0af8d76c54406567a296934a40bab313800b3e0e2d` |

The locally downloaded JSON represented OpenLigaDB match
`83156`, Bundesliga 2026/27, **Bayern München vs VfB Stuttgart**,
kickoff claim `2026-08-28T18:30:00Z`, provider team IDs 40/16.
It declared `matchIsFinished=true` and exactly one result with
`resultTypeKind=After90Minutes`, home **5**, away **1**.
The provider's `lastUpdateDateTime` was
`2026-09-02T15:36:25.313` **without timezone**. Do not promote that
field to a verified timestamp or assume the data existed prior to
the 2026-11-15 read.

The actual JSON response was **not** added to the public repository.
Only the **observed** URL, date claims, byte length, SHA and descriptive
result are recorded in
`ops/research_manifests/openligadb_bl1_2026_match83156_result_original_20261115.json`.
A GitHub commit can confirm this **metadata was subsequently published**,
but it does not prove the HTTP response came from that provider at the
claimed date, nor any pre-match availability or bookmaker edge.

## 3. Checked-in real-byte replay and fail-closed controls

`ops/vnext_openligadb_offline_original.py` is a **no-network** optional
research entrypoint. It only accepts a local copy of this one exact
response. It rejects:

- Missing/altered bytes, file length or SHA-256 mismatch, symlinks and
  nonregular files
- Wrong match ID, league/season, teams or kickoff time
- Unfinished matches, missing/duplicate `After90Minutes` result or
  invalid score, malformed JSON, duplicate object keys and NaN
- A claimed HTTP Date / local-time relationship inconsistent with
  the historical after-90-minutes observation

Run with the **separately obtained, unchanged** provider original:

```sh
python -m ops.vnext_openligadb_offline_original \
  --original /private/originals/openligadb-83156.json
```

The offline real provider JSON was successfully replayed from immutable
GitHub PR code on an external sandbox; **14 synthetic unit tests OK**
(no fetching in CI). An explicit **real negative test** changed the
actual 90-minute result from 5 to 6 without altering the original
2,508-byte length: the CLI rejected it with exit 1,
`OFFICIAL_RESULT_ORIGINAL_BYTES_NOT_PRESENT_OR_CHANGED`.
For the authentic fetched bytes, CLI returned
`source_original_sha256_verified=true` but **`status=HOLD`** and
`production_recommendations=DISABLED`.

### Important: SHA does not prove source or capture authenticity

This experiment confirms that a local file reproduces **those exact
bytes observed in the sandbox**. No independent operator verified the
TLS session, HTTP headers, host ownership or local clock; there is no
provider-signed response, trusted time log, independent result source,
official fixture identity corroboration or independently approved
data-rights integration. The receipt's time fields are explicitly
`*_unattested`, not retrospective signed evidence.

The remaining gate for real certification requires an approved,
source-bound producer, trusted capture-time attestation and independent
cross-provider result verification. **OpenLigaDB supplies no public
immutable historical snapshot service**, so a retrospective API call
cannot demonstrate what was available before any match kickoff.

## 4. No sample/production promotion

This example is **not one of the 104 archived
`evidence/settled.json` results**. It is one distinct historical
fixture used to test the ingestion and archive identity controls,
not an additional settled model forecast. No model, bookmaker price,
profitability or xT/VAEP score has been derived from this original.

- `certified_prospective_samples=0`
- `result_truth_verified=false`
- `publisher_identity_independently_verified=false`
- `capture_time_independently_attested=false`
- `provider_independence_from_other_results_authenticated=false`
- `commercial_licence_fully_cleared_for_deployment=false`
- `positive_ev_verified=false`
- `eligible_for_model_scoring=false`
- `production_recommendations=DISABLED`

PR #436 remains Draft and unmerged; `main` governance blockers
remain [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439).
No raw provider response, personal tokens, secrets or private odds were
uploaded. The external sandbox is separately torn down after verification.
