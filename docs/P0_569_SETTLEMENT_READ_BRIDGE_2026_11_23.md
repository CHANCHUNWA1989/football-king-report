# P0 #569 — Offline settlement read compatibility bridge (2026-11-23 HKT)

**Draft research only — do not run as a production iPhone reader.** This follows the separate provenance-writer pilot in PR #571 and does **not** change any existing GitHub Actions workflow.

## Current verified legacy baseline
- `main:evidence/settled.json` at blob `f546c96def382659ee9d74d6ef40e823a223e4a9` contains **105** research-only samples, `checked_utc=2026-11-21T02:56:04.039201+00:00`, `results_independently_verified=false`, `profitability_verified=false`, `production_recommendations=DISABLED`.
- `.github/workflows/football-king-iphone.yml` passes `evidence/settled.json` to its `--previous` scoring step and a public recommendation-readiness step. It also reads `research_pairs` from main. A branch switch without consumers migration would silently lag or lose visibility.

## New isolated settlement read bridge
- `ops/isolated_settlement_bridge.py` is a **READ-ONLY** library and diagnostic CLI. Requires the legacy evidence file (never silently use empty history), plus a local archive checkout and a trusted 40-character commit SHA. It checks local checkout `git rev-parse HEAD` matches that SHA and reads only a strict `settlement_batches/YYYY/MM/DD/RUN-ATTEMPT.json.gz` namespace.
- Uses bounded gzip reading (max 8 MB per document, 32 MB total, max 256 files), rejects all symlink files, unexpected archive paths, duplicate JSON keys, non-finite numbers, invalid dates and untrusted/bad evidence.
- Reuses existing `ops/evidence_merge.validate` and `merge` to preserve all legacy samples, deduplicate identical replay and **reject changed results for the same fixture**. Aggregated material remains `results_independently_verified=false`, `profitability_verified=false`, `production_recommendations=DISABLED`. Result is returned in memory only; diagnostic CLI prints a bounded receipt and never writes files.
- `ops/tests/test_isolated_settlement_bridge.py`: local real-Git checkout tests plus adversarial fixtures for historical preservation, correct new sample count, repeated same-key data, conflicting final result, absent archive, wrong archive SHA, symlink/extra path, duplicate JSON, gzip decompression limit, missing legacy and conflicting multiple batches. **18 offline tests**, including an exact file-preservation replay of the checked-in 105-sample legacy research evidence and three adversarial pinned-tree blob tests.

## New opt-in isolated settlement writer (same Draft PR)
- `ops/isolated_settlement_archive.py`: checks **mandatory legacy `evidence/settled.json`**, incoming settlement schema and every already archived isolated batch **before** committing a new one. No fixture with a conflicting stored result may be appended. Validates the exact fixed `refs/heads/research/forward-provenance-archive` ref (must already exist), non-force push, bounded gzip and strict `settlement_batches/YYYY/MM/DD/RUN-ATTEMPT.json.gz` paths.
- Same-run, same-byte replay is idempotent; a different byte representation for the same run/attempt is rejected even if its JSON is semantically equivalent. Failures never silently drop historical main samples or alter main.
- `ops/tests/test_isolated_settlement_archive.py`: **11 local bare-Git integration methods** verifying actual branch append, reader round-trip, replay, second independent batch, mandatory legacy, repeated-file collision, cross-batch and cross-main outcome conflict, unsafe source, invalid ID/day, provenance-folder coexistence and unchanged main SHA.
- Both writers are independent **opt-in library/CLI experiments**. No scheduled job or authenticated remote GitHub archive writes are configured; the archive branch is not provisioned by this PR. No signed manifest or real immutable third-party custody is proved.

### Security regression: a matching HEAD SHA did not pin file bytes

Test-first commit `f53439777a7f1656f08e17d6804a93a67058735c` added three **adversarial red tests**. [Failover CI #45163589504](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45163589504) failed all three: `HEAD` SHA stayed identical while a tracked gzip changed, an untracked valid settlement gzip was injected, or an untracked gzip hidden by `.gitignore` was injected; the old bridge silently read the modified/injected bytes.

Repair commit `4a4c3b871486d945952d3d6692346a644f569390` added **per-batch byte-to-Git-blob verification**. The reader first obtains the pinned commit's exact Git tree blob object ID for each allowed `settlement_batches/...` file, reads the compressed file bytes once, hashes *those exact same bytes* as a Git blob and compares object IDs, then decompresses *those same captured bytes* within size bounds. A dirty file, untracked file, or gitignored untracked file now returns `UNPINNED_ARCHIVE_BLOB` instead of being silently counted as a fixture or a settled match. This handles the immediate local-worktree integrity gap, **not** authentication of the externally supplied archive SHA or trusted third-party custody.

Repaired [Security CI #45163806844](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45163806844) raw log confirms **17/17 read-bridge tests**, including all three repaired negatives, and **2,388/2,388 ops, 117/117 V4.1 PASS**. All five workflows on the repair commit succeeded. These are synthetic adversarial checks; archive branch remains unprovisioned remotely and `main` unchanged.

### Fixed remote identity correlation (new research-only gate)

- `ops/archive_remote_ref_gate.py`: strictly pins a **read-only** Git probe to the configured GitHub HTTPS repository `https://github.com/CHANCHUNWA1989/football-king-report.git` and the **fixed** `refs/heads/research/forward-provenance-archive` ref. It requires `origin` in the local checkout to match the pinned URL, an exact matching local `HEAD`, and an exact SHA currently advertised by the specified remote ref (`git ls-remote --heads --exit-code`). Fails closed on wrong/missing branch, moved ref, redirected `origin` or wrong checkout.
- Rejects local Git `url.*` rewrites and `include.*`/ `includeIf.*` config; it ignores Git global and system config during the probe. No fetch, push, branch creation, workflow modification or credential setup.
- `ops/isolated_settlement_bridge.py` retains the standalone **local/offline** mode and marks its receipt `remote_ref_checked=false`. A new opt-in `reconcile_official_remote` / CLI `--require-official-remote` checks the fixed remote ref **both before and after** the pinned, per-file Git-blob-verified settlement read. Successful mode still reports `remote_identity_independently_attested=false` and `production_recommendations=DISABLED`.
- `ops/tests/test_archive_remote_ref_gate.py` runs **12 offline real bare-Git** adversarial tests for correct synthetic remote correlation, moved or deleted ref, main-only ref, re-pointed `origin`, missing origin, invalid SHA/repo root, and malicious Git URL rewrite and include config. One additional bridge case confirms a matching local SHA without official GitHub remote is rejected in strict mode.
- **Limits:** This only correlates what the configured Git server advertises at read time. It **cannot independently prove** original data origin, uploader rights, immutable server branch history, official settlement truth, trusted timestamp, or a live canary. The real GitHub archive branch has not been provisioned or protected by this draft, and there is no automatic iPhone-reader cutover.

### Safety limits
- **Not a deployed read path**; `main` still holds official existing research snapshot; this pilot now includes an **opt-in offline writer candidate**, but no live producer/workflow is switched on and no real remote archive branch is provisioned.
- Pinning the Git commit SHA only checks the local checkout against a **caller-supplied** SHA; it does **not** authenticate who supplied the SHA, give third-party custody, verify a trusted TSA, validate true kickoff/result data, or license a feed.
- The diagnostic CLI does not write merged evidence. A later independent-review cutover must explicitly define the trusted archive-ref fetch, stable consumer manifest, baseline byte-for-byte read parity, fail-closed fallback, and migration of all `archive` direct-main writes including `gh api PUT evidence/settled.json`.
- Existing `archive` five-PUT failure on run #45149415323 remains not fully diagnosed; failed subprocess stderr was deliberately suppressed by the incumbent workflow. Do not invent a cause or assume GitHub Ruleset did it.
- Main no-bypass Rulesets proposed in #439 still **Disabled and not activated**; #569 remains open.

## Technical acceptance

1. Exact-head PR #571 CI, including five provenance writer, eleven isolated-settlement writer and fourteen settlement-read compatibility tests; inspect raw CI logs.
2. Independent code reviewer confirms immutable batch semantics and that no legacy sample can be silently removed or overwritten.
3. Finish authorizing and independently reviewing the existing offline settlement writer; add a trusted manifest and rollback plan, then migrate mobile consumers. Test byte-level output parity on a *real verified* test run; preserve original old main archive.
4. Only after full read/write cutover + independent approval, administer actual protected main Ruleset with no bypass.

No production recommendation, positive EV, official result attribution, real bookmaker odds or release authority is established.
