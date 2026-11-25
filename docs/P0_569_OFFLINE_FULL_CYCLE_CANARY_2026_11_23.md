# P0 #569 — Offline full-cycle two-writer archive canary (2026-11-23 HKT)

**Status: Draft research only. No actual GitHub archive-branch provisioning, credentials, production workflow changes, source authorization or model promotion. HOLD / DISABLED.**

## Why this milestone matters

Separate writer and reader unit/integration tests do not by themselves prove that both opt-in writers safely share a *single* pre-existing archive branch and preserve its committed contents. This adds a single real **local bare-Git** sequence to catch cross-writer folder/branch interactions before requesting authorization for any authenticated remote synthetic canary.

## Test evidence and scope

File: `ops/tests/test_archive_full_cycle_canary.py`.

The test creates a temporary local bare repository and local clone. It commits a synthetic sentinel to `main`, then explicitly provisions `research/forward-provenance-archive` **only in that temporary fixture**. It:

1. Appends a strictly allowlisted, synthetic ten-file provenance proof via `ops.isolated_provenance_archive.append`.
2. Appends a separate synthetic, research-only settlement JSON batch using `ops.isolated_settlement_archive.append` to the same Git archive ref.
3. Checks there are ten immutable `forecast_provenance/` files plus exactly one `settlement_batches/` gzip batch. Reads back original proof bytes and cumulative legacy-plus-new data from a fresh checkout pinned to exact Git SHA.
4. Requires both writer replay calls to report `ALREADY_ARCHIVED` without changing the archive SHA.
5. Requires changed proof bytes and changed same-run settlement bytes to be rejected, leaving the archive ref unchanged.
6. Requires a missing isolated ref to fail rather than silently writing to `main`.
7. Rechecks remote `refs/heads/main` SHA and original legacy file bytes remain unchanged.

Remote-ref correlation is tested **only against a local bare Git fixture** via the offline helper. It does **not** authenticate the origin of any real GitHub ref, prove branch protection or independent custody, or establish signed football results. Only fake research keys `synthetic-legacy` and `synthetic-new` are used. No bookmaker data, commercial market feed, 2026 real match result, positive EV claim or live bet is introduced.

Run when checking out this exact research PR:

```bash
python -m unittest ops.tests.test_archive_full_cycle_canary -v
```

**Acceptance is not assumed from file creation.** Require GitHub Actions results and raw test logs on the **exact latest PR head SHA**, plus independent human review. An older green SHA is not acceptable after edits.

## Still blocked before a real remote canary or cutover

- An owner-approved authorization plan for creating the fixed archive branch, enforcing no-force/no-main-write controls, bounded sandbox fixture retention and rollback.
- Independently reviewed credentials/scope; archived proof must contain only public synthetic data, not real licensed/private provider payloads.
- Capture authoritative remote head SHA before and after and confirm the real `main` SHA is unchanged; exercise idempotent replay, attempted collision and remote read-back.
- Migrate *both* production direct-main writers **and all downstream readers**, including the current iPhone official-readiness/daily-scorecard mixed source. Prove complete historical settlement parity without overwriting original 105 research cases.
- Obtain independent review of PR #571 and preserve `HOLD / DISABLED`. Main no-bypass Ruleset #439, licensed-source approval #452 and #569 remain blocked.

**No live remote branch, workflow, Ruleset, source or site is changed by these tests.**


## Writer push-target identity preflight (new P0 research gate)

The first research writers used `git push origin HEAD:refs/heads/research/forward-provenance-archive`. This is not enough to prove the actual remote destination: Git permits `remote.origin.pushurl`, `remote.origin.mirror`, local `url.*.insteadOf`, `include.*` and other configuration that can redirect or expand Git writes while `remote.origin.url` still looks correct. A non-force push could target the *wrong repository*, or mirror more refs than intended. **No actual misdirected push was observed; this is a discovered pre-release risk.**

New `ops.archive_remote_ref_gate.verify_archive_writer_origin` is a **read-only fail-closed gate**: checks local worktree root, exact origin (pinned to `https://github.com/CHANCHUNWA1989/football-king-report.git` for official entrypoint), rejects alternate push URLs, duplicate origin URL fan-out, mirror/receive-pack/upload-pack overrides, local include and URL rewrites, and requires that a fixed existing isolated remote branch is visible. The shared Git subprocess environment ignores inherited `GIT_*` overrides, global and system config. It records `push_target_config_verified=true` but **explicitly false** for independent review and effective branch protection.

Both `ops.isolated_provenance_archive` and `ops.isolated_settlement_archive` CLI `main()` functions now use `append_official` wrappers that verify this exact remote configuration **before and after** calling the writer. Existing lower-level `append` remains available solely for **offline bare-Git synthetic tests** (and is **NOT safe as an approved authenticated writer**). A future official iPhone workflow must use a reviewed, guarded CLI, **not** call the lower-level test function.

`ops/tests/test_archive_remote_ref_gate.py` adds eight real local Git adversarial checks: correct test-only writer receipt, malicious `pushurl`, duplicate `origin.url` entries, mirror, include, URL rewrite, hooks, missing archive branch and untrusted origin. `ops/tests/test_archive_full_cycle_canary.py` adds one case requiring **both official CLI wrappers** to reject a local-only origin without modifying the temporary archive or main. This is a configuration safety test, **not** a live GitHub remote write or verified permission/ruleset.

**Additional requirements before any real remote canary:** independent reviewer must audit Git credential scope, repository ruleset/branch protection effective states, all Git configuration sources, mutation timing/races and official-ref append-only retention. Observing a URL/ref does not prove these controls or authorize any production feed. Keep `HOLD/DISABLED`.
