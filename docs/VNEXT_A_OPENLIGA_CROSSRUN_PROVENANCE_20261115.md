# PR #458 — Existing signed OpenLigaDB source vs original A raw-byte cross-run reconciliation

Date 2026-11-15. **Open / Draft / Unmerged / HOLD / DISABLED.**

## Why this is more than a new hash utility

Before adding a duplicate capture/signature implementation, the repository was inspected:
- Existing `ops/openliga_capture_pack.py` preserves exact OpenLigaDB original raw bytes in a canonical, bounded `openliga-capture.tar` (with original raw bytes, manifest, capture summary and ODbL 1.0 notice).
- Existing `ops/openliga_capture_provenance.py` performs **fresh** signed-subject verification via `gh attestation verify`, compares expected workflow/certificate source identity and trusted Rekor timestamp, then replays the raw tar. It does **not** authenticate publisher truth, live final score, or the model.
- Existing `ops/archive_openliga_capture.py` saves these bytes into an immutable daily directory with no-replace publication.
- Existing `ops/archive_forecast_provenance.py` and `ops/forecast_provenance_audit.py` handle *separate* original A shadow/paired/slate GitHub-generated subjects.
- These TWO independently operated capture paths do not automatically assert identical source response bytes or identical forecast run.

## Genuine repo artifacts identified (not copied, no new live provider traffic)

Pinned existing `main` ref at `adce289eab28b7b4da9bef2431159ef8d6572ac1`:

- OpenLigaDB canonical signed-origin **capture compressed subject**, `openliga_capture_provenance/2026/11/15/43694406097-1/openliga-capture.tar.gz` — 18,026 compressed bytes, Git blob `e08f9ac613618a67e27710c7496b5f01128b2230`.
- Original A research forecast **shadow compressed subject**, `forecast_provenance/2026/11/15/43694349598-1/shadow.json.gz` — 10,262 compressed bytes, Git blob `b422bd6e129bb1b80822982f3bb0c047086c524c`.
- Other seven 2026-11-15 forecast archives exist, but this current narrow check selects **one exact A subject** and **one exact raw OpenLigaDB subject**, never iterating dates until it finds a lucky match. It is not a statistically representative cohort.
- Attached stored signature bundles `capture.sigstore.json.gz` and `research.sigstore.json.gz` are retained by `main`; **they are NOT authenticated by this offline comparison itself.** The existing upstream provenance auditors must be run freshly in a trusted environment against their original-main signed subjects.

## New code / trust boundary

`ops/original_a_openliga_raw_replay_gap.py` and `ops/research_manifests/openliga_original_a_crossrun_20261115_pinned.json`:
1. Re-read **exact compressed bytes** of the two already-tracked source files using the explicitly pinned original main Git blob IDs, byte limits and safe regular-file access (no new raw provider bytes or provenance bundle added to the PR). Any bit mutation invalidates the pins, no silent repin.
2. Bound decompress each gzip. Pass the raw original canonical tar to existing `openliga_capture_pack.validate_capture`, which checks exact source receipt, raw hash, canonical tar entries and source usage notice. This is a local original-byte replay only, NOT cryptographic signer verification.
3. Open original A `shadow.json` JSON with duplicate-key, schema, disabled-status and count checks. Compare source response digest from original A source receipt and per-forecast same-response typed native IDs **against the exact raw OpenLigaDB matchID, leagueId, leagueSeason, home/away teamId and kickoff**. No fuzzy display-name joining or substitute later source. A separately captured response matching by fixture name/date but not by exact SHA256 cannot pass.
4. Enforce source capture completion no later than original A model timestamp, as claimed by the archived source and A outputs. Chronology alone does not establish independent record custody. If source completed later, the crossrun pair cannot be treated as input available to that A forecast.
5. Always return **HOLD / DISABLED**, even for perfectly byte-matched data. All source/forecaster identity, publisher truth and third-party timestamp certification flags are **false**. The output never includes raw proprietary odds, bankroll sizing or positive EV.

`ops/tests/test_original_a_openliga_raw_replay_gap.py` exercises a **synthetic canonical OpenLigaDB tar built with the repository's existing original archiver**, and adversarial tests for mismatch, unknown/swap IDs, post-A source capture, forged metadata, broken gzip, malicious filename and false signed-source claims.

`.github/workflows/penaltyblog-two-model-pipeline.yml` runs those tests and replays the two **actual pre-existing 2026-11-15 Git-tracked gzip bytes** from a PR checkout. It does not fetch any provider URL, does not deploy, does not install Penaltyblog into `main`, and does not copy the source or forecast into new files.

Use the research diagnostic from repo root:

```sh
python -m ops.original_a_openliga_raw_replay_gap \
  --manifest ops/research_manifests/openliga_original_a_crossrun_20261115_pinned.json \
  --repo-root .
```

This exit status only confirms successful local byte/inventory inspection; never a signed/verified model-forecast outcome.

## Remaining highest-priority blocker

A true same-response bridge requires **the exact original A producer's source response bytes from the same observed GET**, original native-ID link, and verifiable trust chain. A *different* OpenLigaDB source collector run signed under a separate workflow is not automatically the same response used by original A; it may be captured after forecast production.

For even a structural same-response match, a future audited research run must then invoke **both existing original-main signature auditors afresh** (GitHub-approved signer identity, exact run ID/attempt, Rekor timestamp), bind their independently verified subjects and source chronology, and ensure historical data rights. Existing saved verification reports, self-generated SHA256 and Git blob hashes are insufficient for independent authentication. The approach must not create post-hoc signed claims for old unsourced forecasts.

Keep `certified_prospective_samples=0`, `positive_ev_verified=false`, `production_recommendations=DISABLED`, no independent betting EV or model comparison claims. Open Draft PR #458 and independent governance Issue #439 remain blocking; no merge.
