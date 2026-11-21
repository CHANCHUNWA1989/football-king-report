# PR 460 — Actual original A-forward compressed archive replay (2026-11-15 UTC)

Research only. All results HOLD / DISABLED, not a certified OOS, EV or source authentication.

## Seven genuine Github compressed snapshots inspected

The original main repository's immutable commit adce289eab28b7b4da9bef2431159ef8d6572ac1 contains seven compressed original research files in research_pairs/2026/11/15. Each exact path, original compressed byte count and Git blob SHA-1 are pinned separately in ops/research_manifests/original_A_forward_pairs_20261115_pinned.json. No copyrighted third-party match source bytes were added by this research PR.

[Research CI run #43698908806](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/43698908806), at commit 2751115a25b4f823a2547ea1645b1cdf5b756396, actually verified and decompressed all seven tracked files. Observations across those seven archives: **147 research comparison ROWS, not 147 independent matches**. All 147 rows had an original A model 1X2 probability-vector observation, a market probability vector, legacy AB shrinkage model and legacy C market-anchor model. Native Penaltyblog forecast snapshots: **0**. Independently authenticated same-fixture prematch A/Penaltyblog pairs: **0**. Executable bookmaker quote, signed publisher original, trusted forecast time and independently authenticated score from this audit: **0**.

## New files and tests

- ops/archived_forward_model_coverage.py: a bounded, offline read-only compressed-byte verifier and research-shape inventory. Fails closed on wrong Git blob hashes, malformed gzip or JSON, expansions over 8MiB, duplicate JSON keys, symlinks, changed input size, unknown challenger labels, Boolean or nonfinite probability values, injected Penaltyblog fields, missing/duplicate file entries and any enabled production flag. A success exit status means only that local bytes and internal structure matched the selected historical version.
- ops/tests/test_archived_forward_model_coverage.py: **18 adversarial synthetic regression tests passed** in exact-head research CI, plus the seven real original compressed files replayed separately in the same job.
- ops/research_manifests/original_A_forward_pairs_20261115_pinned.json: the historical seven-file immutable-Git-object identity manifest.
- .github/workflows/paired-challenger-comparison.yml: adds a read-only verification step; doesn't alter production/main.

The 147 observations might repeat the same fixtures across seven different runs. They have NOT been deduplicated into an independent prospective sample. This inspector does not test signer keys or attested capture times. A Git SHA-1 proves relative Git object identity only, never the external score or timestamp truth.

## What is still needed

Independent authorization for the actual data source; genuinely archived new *before-kickoff* original A plus Penaltyblog Poisson and Dixon–Coles outputs with matching native fixture IDs and UTC decision cutoffs; independently witnessed source/forecast chronology; independent final results and authentic time-aligned market quotes. Merely reprocessing previous matches now cannot create prospective evidence.

The optional Penaltyblog technical prototype remains separate in [Draft PR #458](https://github.com/CHANCHUNWA1989/football-king-report/pull/458). No merge of it into A has occurred, and legacy AB/C are not Penaltyblog. Main branch protection, an independent human review and a real signer still blocked by [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439).

PR #460 remains OPEN / DRAFT / UNMERGED; certified_prospective_samples=0, positive_ev_verified=false and production_recommendations=DISABLED.
