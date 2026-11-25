# P0 #569 — prevent generic append-helper bypass of hosted archive lock

**Date:** 2026-11-23 HKT. **Scope:** research PR #571, not deployed. **Decision:** HOLD / DISABLED.

## Reason for this change

The owner-visible GitHub archive branch `refs/heads/research/forward-provenance-archive` now exists at `3ce493fbeb9bfea29af1b93064a085afe8efb280`, equal to the observed `main` commit. Its existence is NOT an independent permission audit, review, immutable storage proof or authorized write canary. The official `append_official()` wrappers were already blocked by `ops/archive_hosted_write_lock.py`, but the lower-level `append()` functions, intended solely for temporary bare-Git fixtures, still accepted any reachable `origin`.

This milestone closes that **direct import / alternate invocation gap** without touching live GitHub archive data, credentials, workflows, Rulesets or `main`.

## Changed research-only files

- `ops/archive_local_fixture_guard.py`: read-only conservative origin validator for the **generic** test-helper functions. Exactly one `remote.origin.url` must be an absolute local filesystem path to an ordinary bare Git repository. Rejects HTTP(S), SSH, scp syntax, `file://`, relative paths, symlink aliases, duplicate origins, `remote.origin.pushurl`, push refspecs, mirror flags, remote command overrides, Git URL rewrites, includes, credential helpers and `core.hooksPath`. Does not print remote URL, secrets, or raw config. The receipt explicitly states `hosted_archive_write_authorized=false` and `production_recommendations=DISABLED`.
- `ops/isolated_provenance_archive.py` and `ops/isolated_settlement_archive.py`: invoke the local-only check **before any remote query/fetch/push** by the generic helper and again immediately before its permitted *local-fixture* push. If rejected, no fallback to another ref or to `main` occurs.
- `ops/tests/test_archive_local_fixture_guard.py`: **9** real temporary bare-Git tests validating allowed local fixtures and rejected hosted origins, redirectors, mirrors, duplicate URLs, symlinks, nonbare targets and missing remote. The two generic `append()` functions are tested with a GitHub URL while remote-query methods are mocked and asserted **not called**, avoiding any network operation.

No production deployment is enabled. Generic `append` remains available only for offline fixtures; both official wrappers remain **hard-locked** pending a separate, independently reviewed policy/identity/storage change.

## Exact-head CI evidence

Checked GitHub PR research head `90215f7f0ff65882234a2dfcb490ea3bef9da841`:

- [Security regression #45178924662](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45178924662), raw regression job `137707431094`: all **9/9** `test_archive_local_fixture_guard` tests `ok`, **2,489 ops** tests and **117 V4.1** tests completed successfully.
- [Archive bootstrap read-only #45178924725](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45178924725), [Failover #45178924750](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45178924750), [Repository Safety #45178924655](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45178924655), [Offline 1X2 #45178924718](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45178924718), [Unified Ledger #45178924758](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45178924758) — SUCCESS.
- Total **6/6** exact-head workflow conclusions SUCCESS. This establishes CI/test behavior only, not independently attested GitHub protection.

## Residual risk and owner/reviewer dependencies

- A local filesystem path can itself refer to a network-mounted filesystem; this is a conservative **Git configuration safeguard**, not proof of OS-level sandbox isolation or a true remote-enforcement boundary. Only run generic helpers in an independently isolated test runner. Do not import them in production jobs.
- This lock is in a **Draft research PR**, not `main`. Deployed legacy workflows still contain four direct `main` Git push blocks and 14 workflow-file Contents API mutation indicators. No claim that public deployed workflows have been modified.
- `main` reported `protected:false`, repository `rulesets=[]`, no independent human reviewer recorded. There is no independently verified archive branch protection, actor permission denial to `main`, real synthetic-only GitHub push/readback canary, full producer/reader migration or data licensing.
- Owner should appoint a non-author reviewer, approve actual isolated storage/actor permissions, capture effective GitHub policy and denied-main-write evidence, and only then review a separate controlled write canary proposal. No environment switch, automated unlock or self-review is acceptable.

**Leave PR #571 Draft, issues #569/#439/#452 open, `main_ruleset_activation_authorized=false`, `production_recommendations=DISABLED`.**
