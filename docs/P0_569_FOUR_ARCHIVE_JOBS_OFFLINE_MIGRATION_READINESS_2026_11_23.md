# P0 #569 — P0-A four archive-job offline migration readiness

**Date:** 2026-11-23 HKT. **Status:** Draft research, HOLD / DISABLED. No workflow deployment, source admission, credential change, branch protection change or hosted Git write.

## What the direct-main audit actually found

Two existing workflows still contain four direct-main Git push job blocks on deployed `main`:

| Workflow | Job | Proposed archive content | Pilot status |
|---|---|---|---|
| `football-king-iphone.yml` | `archive_provenance` | Exact forecast-provenance evidence batch under `forecast_provenance/` | Offline local bare-Git tested |
| `football-king-iphone.yml` | `archive` | Research history and cumulative settlement; isolated append under `settlement_batches/` | Settlement batch offline tested; historic archive families/read parity **NOT** migrated |
| `four-model-shadow-daily.yml` | `archive_ndr_capture` | Original `ndr-capture.tar` and `capture.sigstore.json`, stored as deterministic gzip under `ndr_capture_provenance/` | **New** offline local bare-Git writer tested |
| `four-model-shadow-daily.yml` | `archive_openliga_capture` | Original `openliga-capture.tar` and `capture.sigstore.json`, stored as deterministic gzip under `openliga_capture_provenance/` | **New** offline local bare-Git writer tested |

**These are four write-capable job blocks, not four independently deployed migrations.** Existing main workflows still push directly to `main` and other 14 workflow files contain Contents API mutations.

## New code and exact acceptance evidence

- `ops/isolated_capture_archive.py` is a **local bare-Git fixture-only** opt-in research helper with a fixed non-main `refs/heads/research/forward-provenance-archive`, strict `ndr` / `openliga` family allowlist, immutable original tar/sidecar bytes, deterministic gzip archive helpers, fixed non-force push, replay/collision checks, and pre-/post-`main` SHA check.
- It calls `ops.archive_local_fixture_guard.require_local_fixture_git_origin` before remote operations and immediately before any local-fixture push. A GitHub/SSH/HTTP(S) origin is rejected before network access. No official hosted CLI is provided for this prototype, and **nothing authorizes** use of the helper against hosted Git.
- `ops/tests/test_isolated_capture_archive.py` tests both families sharing one temporary bare Git repository, byte-identical Git-blob readback, replay as a no-op, collision rejection, absence of archive ref, invalid family and GitHub URL refusal.
- Exact tested commit `014d1688e774ecb0153bcf75da3446126939a793`: [Security regression #45181795283](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45181795283), raw job `137717245004` shows all **6/6** new tests `ok`; **2,512 ops** and **117 V4.1** tests complete. [Failover #45181795148](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45181795148), [Repository Safety #45181795195](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45181795195), [Offline 1X2 #45181795211](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45181795211), [Unified Ledger #45181795196](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45181795196), [Archive Bootstrap Readonly #45181795136](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45181795136): **SUCCESS**. All **6/6 workflows** passed this exact code SHA.

## Why this is still not cutover authorization

1. Real `refs/heads/research/forward-provenance-archive` exists at bootstrap SHA `3ce493fbeb9bfea29af1b93064a085afe8efb280`, but read-only remote branch-policy probe observed no effective non-fast-forward or deletion rule; classic protection audit was unavailable. Existing `main` returns `protected:false`; repository Rulesets returned `[]`. A ref matching `main` is not an authenticated, protected archive.
2. Actual hosted actor credentials must be proven unable to write `main` under independently enforced policy. A job `contents: write` token is repo-scoped, **not** restricted just because code targets a named ref. Consider separately permission-isolated archive repo/object store.
3. There are **0 independent GitHub PR reviews** recorded. Owner/admin and a genuinely non-author reviewer must approve storage, controls, data rights and scoped synthetic-only remote canary *before any hosted writer can be introduced*.
4. The NDR/OpenLiga tar and sigstore sidecars in the tests are **fake fixtures only**; byte equality is not signature authentication, timestamp witness, real result validation, source licensing or truth of any `verified` flag.
5. `football-king-iphone.yml` still contains original archive family writes and split settlement consumers. Source/market mutable pointers and the 15-workflow write matrix require complete producer and reader parity before a no-bypass `main` Ruleset.
6. Do not unlock `ops.archive_hosted_write_lock`, link generic append helpers to GitHub, merge or self-approve; do not force push, delete archive history, write to `main`, approve fake evidence, or enable betting.

## Next owner/reviewer acceptance

- [ ] Record non-author reviewer and exact approved commit, independent source rights and protection of public/private materials.
- [ ] Admin independently configures/attests effective archive storage access, non-force/non-delete controls, bypass actors and write-to-main denial without admin PAT in Actions.
- [ ] Approve a bounded **synthetic-only** hosted canary, with pinned before/after main + archive SHAs, original blob digests, replay, collision refusal and readback. Do not run it under unreviewed configuration.
- [ ] Design migration for all four job blocks and separate later read compatibility for iPhone official-readiness/daily-scorecard and source/market latest/history.
- [ ] Recheck all 15 workflows and unique required CI contexts before #439 no-bypass main Ruleset can be activated.

**`main_ruleset_activation_authorized=false`, `remote_canary_write_verified=false`, `production_recommendations=DISABLED`. Keep #569 / #439 / #452 open.**
