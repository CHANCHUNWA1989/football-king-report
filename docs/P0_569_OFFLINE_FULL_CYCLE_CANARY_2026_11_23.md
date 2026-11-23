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
