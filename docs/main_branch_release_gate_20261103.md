# P0: Main-branch writer isolation — release preflight (2026-11-03)

**Status: NOT APPROVED FOR MAIN PROTECTION, MERGE, OR BETTING RELEASE.**

This document is an operational handoff, not a claim of independent review,
provider evidence, branch-rule enforcement, or a deployed fix.

## Verified current facts

- `main` was still receiving bot-authored source/archive updates on 2026-11-03.
  A main commit observed at that time was `848eedb112cd26a850df23a7a9a90cf84129f706`,
  entitled "Archive optional Asia weather and K League partner status; no odds or key".
  This confirms the branch remains a mutable archive surface.
- `.github/workflows/football-king-odds.yml` has an `archive` job with
  `contents: write` and GitHub Contents API PUT calls to
  `market/history/*`, `market/collection_status.json`, and `market/latest.json`.
- `.github/workflows/football-king-bsd-free.yml` has an `archive` job with
  `contents: write` and PUT calls to `sources/bsd_history/*` and latest source statuses.
- `.github/workflows/football-king-iphone.yml` reads latest market/source
  artifacts from the checkout and uses successful collector `workflow_run`
  events to refresh the website. A naive change of archive branch will break
  that contract if publishing readers are not migrated and retested together.
- The former six-PR release backlog in Issue #369 has **changed**:
  PR #361, #367, #368, #365 are merged; PR #364 and #362 remain open at
  this inspection. Those two PRs had no formal review submissions.
  A `COMMENTED` review by the repo owner on a merged PR is not independent approval.
- PR #380 is still Draft, with synthetic security tests but no real provider
  source attestation or qualified forward samples. Keep betting disabled.

## Delivered preflight

`python ops/main_branch_writer_preflight.py --root .`

This uses only the Python standard library, reads local workflow files, and
outputs a deterministic JSON inventory of **potential** write-capable workflows
and explicit git-push / gh-API mutation markers. It detects both job/global
`contents: write` and `permissions: write-all`. It never performs network
calls, reads credentials, mutates files, or accesses betting accounts.

`python ops/main_branch_writer_preflight.py --root . --require-no-writer-candidates`

The stricter command exits 2 while any writer candidate is detected, or if
workflow enumeration is missing/invalid. **Neither mode proves branch safety**:
indirect writes through scripts, custom credentials, reusable workflows, and
dynamic endpoint expressions still require manual inspection. Even zero
candidates retains `main_branch_protection_independently_verified=false`.
Do not make this strict mode a required CI check before migration finishes.

## Required migration sequence (not yet executed)

1. **Inventory and map all writer → reader paths.** For every write-capable
   workflow, record exact target files, consumer paths, code ref, trigger type,
   token permissions, and fallback/rollback. Resolve unknown paths manually.
2. **Choose a separately permissioned archive location** (dedicated archive
   branch or controlled store), with constrained credentials. Protect code
   `main` separately. Avoid copying private raw odds, keys, or identifying
   evidence into the public repository.
3. **Migrate one producer/consumer pair at a time on a reviewed branch.**
   Keep original snapshot chronology, hash, deduplication and stale-write
   rejection. Update the website reader explicitly, with strict source ref
   pinning and fail-closed handling of missing, old, or malformed archive data.
   Account for GitHub Actions `GITHUB_TOKEN` commits not triggering ordinary
   push workflows, and independently verify intended `workflow_run` refresh.
4. **Run real, bounded canary and rollback tests** for collector → archive
   → website publish and outage handling. Confirm as-of UTC, permitted API
   quota, latest/history consistency, and no stale downgrade or accidental
   production recommendation. Compare the deployed website with on-disk
   source versions. Do not run paid or extra market calls without authorization.
5. **Only after writers have been isolated**, enable/enforce main branch
   protection/rulesets: required PR review by a genuinely separate authorized
   reviewer, required unique CI checks, no force push/deletion or administrator
   bypass when feasible. Read back enforcement from GitHub's API, then verify
   a prohibited direct push would actually be rejected without performing it.
6. Independently review/merge remaining PRs one by one, rerun checks on
   the exact merge heads, and verify the deployed research site. The private
   quote/Sigstore chain and externally verified forward data remain separate
   blockers for model-certification and any betting release.

## Release rejection conditions

- No externally authenticated pre-kickoff quote/fixture evidence or independent
  forward settlement: `HOLD`, `production_recommendations=DISABLED`.
- No independent reviewer or unverified main protection: do not claim code release readiness.
- Any producer/reader cutover that silently removes data, breaks website refresh,
  or weakens stale/duplicate handling: rollback and restore previous safe behavior.

Tracking: [Issue #56](https://github.com/CHANCHUNWA1989/football-king-report/issues/56),
[Issue #369](https://github.com/CHANCHUNWA1989/football-king-report/issues/369),
[PR #380](https://github.com/CHANCHUNWA1989/football-king-report/pull/380).
