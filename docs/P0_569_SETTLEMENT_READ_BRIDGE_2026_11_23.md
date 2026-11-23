# P0 #569 — Offline settlement read compatibility bridge (2026-11-23 HKT)

**Draft research only — do not run as a production iPhone reader.** This follows the separate provenance-writer pilot in PR #571 and does **not** change any existing GitHub Actions workflow.

## Current verified legacy baseline
- `main:evidence/settled.json` at blob `f546c96def382659ee9d74d6ef40e823a223e4a9` contains **105** research-only samples, `checked_utc=2026-11-21T02:56:04.039201+00:00`, `results_independently_verified=false`, `profitability_verified=false`, `production_recommendations=DISABLED`.
- `.github/workflows/football-king-iphone.yml` passes `evidence/settled.json` to its `--previous` scoring step and a public recommendation-readiness step. It also reads `research_pairs` from main. A branch switch without consumers migration would silently lag or lose visibility.

## New isolated settlement read bridge
- `ops/isolated_settlement_bridge.py` is a **READ-ONLY** library and diagnostic CLI. Requires the legacy evidence file (never silently use empty history), plus a local archive checkout and a trusted 40-character commit SHA. It checks local checkout `git rev-parse HEAD` matches that SHA and reads only a strict `settlement_batches/YYYY/MM/DD/RUN-ATTEMPT.json.gz` namespace.
- Uses bounded gzip reading (max 8 MB per document, 32 MB total, max 256 files), rejects all symlink files, unexpected archive paths, duplicate JSON keys, non-finite numbers, invalid dates and untrusted/bad evidence.
- Reuses existing `ops/evidence_merge.validate` and `merge` to preserve all legacy samples, deduplicate identical replay and **reject changed results for the same fixture**. Aggregated material remains `results_independently_verified=false`, `profitability_verified=false`, `production_recommendations=DISABLED`. Result is returned in memory only; diagnostic CLI prints a bounded receipt and never writes files.
- `ops/tests/test_isolated_settlement_bridge.py`: local real-Git checkout tests plus adversarial fixtures for historical preservation, correct new sample count, repeated same-key data, conflicting final result, absent archive, wrong archive SHA, symlink/extra path, duplicate JSON, gzip decompression limit, missing legacy and conflicting multiple batches. **14 offline tests**, including an exact file-preservation replay of the checked-in 105-sample legacy research evidence.

## New opt-in isolated settlement writer (same Draft PR)
- `ops/isolated_settlement_archive.py`: checks **mandatory legacy `evidence/settled.json`**, incoming settlement schema and every already archived isolated batch **before** committing a new one. No fixture with a conflicting stored result may be appended. Validates the exact fixed `refs/heads/research/forward-provenance-archive` ref (must already exist), non-force push, bounded gzip and strict `settlement_batches/YYYY/MM/DD/RUN-ATTEMPT.json.gz` paths.
- Same-run, same-byte replay is idempotent; a different byte representation for the same run/attempt is rejected even if its JSON is semantically equivalent. Failures never silently drop historical main samples or alter main.
- `ops/tests/test_isolated_settlement_archive.py`: **11 local bare-Git integration methods** verifying actual branch append, reader round-trip, replay, second independent batch, mandatory legacy, repeated-file collision, cross-batch and cross-main outcome conflict, unsafe source, invalid ID/day, provenance-folder coexistence and unchanged main SHA.
- Both writers are independent **opt-in library/CLI experiments**. No scheduled job or authenticated remote GitHub archive writes are configured; the archive branch is not provisioned by this PR. No signed manifest or real immutable third-party custody is proved.

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
