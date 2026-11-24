# P0 #569 — four archive writers with preserved 105+ research rows and both iPhone report builders

**Research-only evidence · 2026-11-23 HKT · PR #571 Draft · HOLD / DISABLED.**

## Why this follows the 15-file four-writer canary

The previous local bare-Git canary proved that four archive jobs can append 15 compressed files to one isolated branch. This acceptance tests the downstream **read** contract using the original checked-in legacy settlement research history and the actual two iPhone report builders. It does not alter the legacy evidence or publish iPhone assets.

New test module: `ops/tests/test_four_writer_mobile_read_parity.py`.

- Reads `evidence/settled.json` from the checked-out research commit as **original research-only** history, asserts at least **105** samples, retains exact source bytes, and preserves `results_independently_verified=false` and `production_recommendations=DISABLED`. It does not fabricate a new real final score.
- Creates exactly **one synthetic-only settlement case** in temporary storage and synthetic evidence files for all four writers (forecast provenance 10, settlement 1, NDR 2, OpenLiga 2).
- Runs all four writers against a **temporary local bare Git** archive, obtains a pinned local SHA, separately checks out the reader, and validates one committed settlement batch with `ops.isolated_settlement_bridge.reconcile`. Non-settlement sibling paths must not be counted as settlement batches.
- Calls `ops.mobile_shared_settlement._assemble`, which uses the **actual** public-readiness and daily-scorecard builders in memory. The candidate has **legacy N + 1** observations in *both* reports. The legacy file and original main sentinel remain unchanged; the existing mobile workflow split remains detected. The preview has `site_published=false`, `archive_ref_independently_attested=false`, `verified_final_scores=false`, `source_switch_authorized=false`, `production_recommendations=DISABLED`.
- Negative tests intentionally remove a historic case, change a historic result, corrupt a checked-out committed gzip blob while keeping the same pinned Git SHA, and introduce an untracked settlement gzip. These conditions must fail closed rather than silently count the untrusted samples.
- Simulates a separate main-only source/status update **after archive bootstrap**, then archives all four synthetic batches. The updated main latest-file stays off the isolated branch, the common ancestor remains the historical base, and both candidate mobile builders still agree at N+1.

## CI evidence pinned to exact code

- Research code SHA **`7f53728cb40c15738cf2cff811bf8dc212af7fa2`**, [safety regression #45191366903](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45191366903), raw job `137750269327`: all **5/5 new read-parity tests PASS**; **2,529 ops tests** and **117 V4.1 tests** complete.
- [Failover #45191366915](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45191366915), [Repository Safety #45191366914](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45191366914), [Offline 1X2 #45191367024](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45191367024), [Unified Ledger #45191366943](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45191366943), [Archive Bootstrap Readonly #45191367096](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45191367096): **SUCCESS**. All **6/6** workflows for the exact code SHA completed successfully.
- A later documentation-only HEAD must be separately checked rather than inheriting this verdict automatically.

## Important separation of test and hosted reality

This test uses an **untrusted local Git fixture** and intentionally invokes only local-test append helpers; it is not an authorized GitHub-hosted writer or credential-scope proof. The official hosted writer entrypoints are **hard-locked** and no production workflow was changed, merged, self-approved or deployed. The site builders are invoked only in process and do not deploy public pages. Test fake tar/sidecar files are not Sigstore verification, licensed source data or independently verified football results.

At entry to the milestone, real `main` was observed at `cb3aa5d44817bfa77a4952ced15d1d4b2df99753`, while the actual hosted archive branch remained at its bootstrap SHA `3ce493fbeb9bfea29af1b93064a085afe8efb280`. These are time-pinned observations and not assertions about future remote state. Repository Rulesets were `[]`, main `protected:false`, and PR #571 had **0** independent reviews.

### Release and governance still blocked

- The real deployed iPhone workflow still has its existing settlement input split and existing direct-main archival jobs. All 15 identified `contents: write` workflows / 14 Contents API mutation-indicator files need controlled source and reader migration; there is no no-bypass Ruleset or independently enforced archive custody.
- No actual remote synthetic GitHub append/readback canary, approved writer identity unable to write main, proven non-force/non-delete protection or independent review.
- No licensed bookmaker odds, authenticated FT/xG or verifiable positive EV for live betting. A successful `preflight` proves internal code/data parity only.
- Require owner-admin effective branch/credential evidence and a non-author reviewer to approve exact HEAD, historical data-retention policy, migration, rollback and a separate synthetic-only hosted canary before any write lock can be removed.

**Verdict: OFFLINE FOUR-WRITER MOBILE READ PARITY PASSED · HOSTED MIGRATION HOLD · PRODUCTION RECOMMENDATIONS DISABLED.**
