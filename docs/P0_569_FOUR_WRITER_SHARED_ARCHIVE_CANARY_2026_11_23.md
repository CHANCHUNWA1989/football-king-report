# P0 #569 — four archive writers, one local bare Git branch: complete integration canary

**2026-11-23 HKT · Draft PR #571 · research-only / HOLD / DISABLED.**

This acceptance proves **offline synthetic plumbing** across all four direct-`main` archive write families. It does **not** establish remotely enforced permissions, actual hosted GitHub append authorization, provider rights, Sigstore validation, authentic match/odds data, investment/betting profitability or a successful production cutover.

## Exact test scope and evidence

`ops/tests/test_four_writer_shared_archive_canary.py` provisions a new **temporary local bare Git repository**, creates its own synthetic `main` and fixed isolated archive ref, and then runs **all four** existing local-only migration writers against the **same** isolated ref:

| Existing deployed workflow job | Offline writer exercised | Synthetic compressed blobs |
|---|---|---:|
| `football-king-iphone.yml:archive_provenance` | `ops.isolated_provenance_archive.append` | 10 forecast provenance files |
| `football-king-iphone.yml:archive` | `ops.isolated_settlement_archive.append` | 1 cumulative-compatible settlement batch |
| `four-model-shadow-daily.yml:archive_ndr_capture` | `ops.isolated_capture_archive.append_capture(kind="ndr")` | 2 NDR capture original-byte files |
| `four-model-shadow-daily.yml:archive_openliga_capture` | `ops.isolated_capture_archive.append_capture(kind="openliga")` | 2 OpenLiga original-byte files |

Expected total: **15 gzip files across four separately exercised writers**. The test pins the local final archive SHA, clones a separate reader checkout, verifies the branch ref and exact compressed-to-original bytes, and independently reconciles legacy+new synthetic settlement (`2` samples, one historical and one new, with all real-source verification flags false).

Six test scenarios passed:
1. Four complete batches written to a single **local** archive, 15/15 exact raw-byte readback, source flags remain disabled and original `main` unchanged.
2. Different interleaving of four writers creates the same four family path sets without overwriting one another.
3. Replaying all four unchanged batches yields `ALREADY_ARCHIVED` without changing the isolated SHA.
4. Changing a run-matched input for each of the four families produces fail-closed collision errors; neither archive ref nor `main` is rewritten.
5. A **synthetic main update after archive-branch bootstrap** remains on local `main`; four subsequent archive writes only change the isolated ref; archived Git tree excludes the synthetic new-`main` latest-pointer file and common merge-base remains the original baseline.
6. With no isolated branch provisioned, all four writers reject instead of falling back to `main`.

The fixtures are deliberate fabrications for testing; no authentication or authenticity is implied by tar/JSON contents.

## Exact-head GitHub CI

Code commit: `b6148e11ea5e52796b6a87a31c4538688587abe8`.

- [Safety regression #45189824219](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45189824219): **SUCCESS**, raw test-job `137744897558` logs all 6 new test names `ok`; **2,518 ops tests**, **117 V4.1 tests** completed successfully.
- [Failover #45189824343](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45189824343), [Repository Safety #45189824391](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45189824391), [Offline 1X2 #45189824328](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45189824328), [Unified Ledger #45189824167](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45189824167), [Archive Bootstrap Readonly #45189824305](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45189824305): **SUCCESS**.
- Thus **6/6 CI workflows SUCCESS for the exact code SHA**. Documentation revisions later than that SHA must be evaluated separately.

## Actual GitHub state is DIFFERENT from local synthetic tests

At the start of this milestone, connected GitHub returned:

- Live `main` at `cb3aa5d44817bfa77a4952ced15d1d4b2df99753`, `protected=false`.
- Existing hosted `refs/heads/research/forward-provenance-archive` at historical bootstrap `3ce493fbeb9bfea29af1b93064a085afe8efb280`.
- Repository Rulesets `[]`; PR #571 Draft/open/unmerged; **0 independent GitHub reviews**.

The values above are time-pinned observations only, not a guarantee that `main` or archive has remained stationary. **An archive fork need not match a live evolving `main` SHA** after migration, but every real cutover requires separately pinned source-history and retention/reader compatibility proof. This offline test intentionally simulates `main` advancing after archive bootstrap; it does NOT retroactively synchronize or copy real `main` source updates into the real archive.

## Release blockers and next owner-controlled steps

- Four direct-main archive jobs are **still deployed to `main` as originally written**, and 14 other Contents API mutation-indicator workflow files require migration/reader compatibility. A proof of isolated archive writes in temporary local Git does not change deployed workflows.
- Current hosted write lock remains enabled for official provenance/settlement entrypoints; generic and capture append functions only accept local bare Git fixture origins. No hosted remote synthetic canary was attempted or authorized.
- No verified effective hosted archive non-force/non-delete policy, writer identity unable to write `main`, no-bypass or admin enforcement, independent human review, and no proven original 105+ research sample read parity in production.
- **Owner and genuinely non-author reviewer** must provide effective policy/bypass/credential-scope evidence and approve a future synthetic-only hosted write/readback canary **before any new writer is linked to hosted GitHub**. No admin PAT in Actions, force-push, direct-main fallback, PR auto-merge, self-approval or betting enablement.
- All work to cut over mutable `latest`/status data needs a separate consumer migration. Protect old main-history byte-level data, keep `main_ruleset_activation_authorized=false`, `production_recommendations=DISABLED`, issues #569/#439/#452 open.

**Result: OFFLINE FOUR-WRITER ACCEPTANCE PASSED; HOSTED CUTOVER UNAUTHORIZED; HOLD / DISABLED.**
