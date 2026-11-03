# P0 BSD archive producer → reader cutover (research-only, 2026-11-03)

**Release status: DRAFT / NOT DEPLOYED / NOT APPROVED.** This is one
isolated optional-source pair, not a completed migration of all main writers.

## Observed initial contract

- `.github/workflows/football-king-bsd-free.yml` collects optional free
  BSD research without publishing raw bookmaker quotes or credentials.
- Its archive job formerly performed GitHub Contents API PUTs directly to the
  default branch for `sources/bsd_history/*`,
  `sources/bsd_status_latest.json`, and conditionally
  `sources/bsd_market_latest.json`.
- `.github/workflows/football-king-iphone.yml` formerly read BSD optional
  data from the default-branch checkout. Successful collector
  `workflow_run` can trigger a fresh Pages build.
- At inspection, `sources/bsd_status_latest.json` was a
  `NO_COMPARABLE_MARKET` research snapshot and
  `sources/bsd_market_latest.json` was absent; neither is a betting quote.

## Proposed cutover in this PR (not active on main)

1. An actual repository branch `archive/bsd-free-research-v1` has been
   created by copying the existing `main` ref. **This is not a data-only
   Git history** and does not provide external immutable retention, separate
   custody, or protected-branch enforcement. Do not execute code from it.
2. The BSD `archive` job pins `BSD_ARCHIVE_REF` to this branch, refuses a
   missing/invalid branch ref before writing, uses a branch-qualified
   Contents API GET on each lookup, and passes `branch` explicitly on every
   PUT. Its existing timestamp/duplicate guard and retry logic remain.
3. The iPhone Pages `publish` job performs a second **read-only sparse
   checkout** of that branch containing only two BSD latest snapshot files.
   It runs the trusted `ops/bsd_archive_reader.py` from the ordinary code
   checkout, rejects symlink/nonregular/oversized archive paths, then passes
   only `bsd-research-archive/sources/bsd_*.json` to the existing vendor
   validation and optional research overlay. There is **no fallback to
   default-branch BSD data**.
4. Missing optional market data yields the existing BSD `HOLD` overlay.
   Stale or forged vendor contents do not become real-money research. The
   main prediction, market pricing, model weights, live betting and quote
   API limits remain untouched.
5. New offline tests pin the exact producer/consumer ref contract, reject
   symlink/oversize/missing-checkout cases and verify optional-source HOLD.

## 2026-11-03 read-only branch checkout and fail-closed bugfix

- **Fixed a stale-data precedence defect** in `ops/bsd_overlay.py`: previously
  the optional market file was read before the status file; if a previous
  research-eligible market remained after a later `NO_COMPARABLE_MARKET`,
  `HOLD`, or `NOT_CONFIGURED` update, the older market could be selected.
  Latest `bsd_status_latest.json` is now authoritative. A
  `RESEARCH_ONLY` status with non-identical/missing market counterpart
  becomes `HOLD` with `INCONSISTENT_BSD_ARCHIVE_PAIR`; missing/invalid
  status becomes `HOLD`, not fallback to historical market.
- **Optional branch outage isolation**: iPhone checkout failure removes
  partial BSD checkout and produces optional `HOLD` without failing the
  primary football website build. When the checkout succeeds, the existing
  read-only symlink/oversize path safety check remains mandatory.
- Added five new archive precedence/partial-write regression tests. New
  `.github/workflows/bsd-archive-readonly-canary.yml` uses read-only
  GitHub access and no provider token, paid API or external data calls.
  Its first attempt had a workflow expression escaping bug, fixed before
  acceptance. Do not cite the failed run as successful.
- **Verified real read-only checkout**:
  [GitHub Actions run #41584038388](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/41584038388)
  checked out `archive/bsd-free-research-v1` at
  `848eedb112cd26a850df23a7a9a90cf84129f706`. Real archived status:
  `captured_utc=2026-11-02T23:39:51.902626+00:00`,
  `NO_COMPARABLE_MARKET`, `market_count=0`, companion
  `bsd_market_latest.json` absent. It ran the optional overlay against
  **synthetic empty shadow predictions**, confirmed `HOLD`, zero pairs,
  no executable market, `production_recommendations=DISABLED`.
  This **does not show** new BSD writes to the branch, fresh archiver
  triggers, a real site publishing from the archive, or rollback completion.
- Exact earlier tested head `43f6b1d91e95922e57d676b52b880784f858e40a`:
  **7/7 GitHub CI workflows passed**, **13/13 targeted new BSD tests**,
  **2311/2311 ops regression**, **117/117 original V4.1**.
  Any later documentation-only head must be revalidated separately.

## Latest S2 optional-source resilience checks (2026-11-03)

- Existing independent code reviewers have **not** approved PR #381 or #382.
  Both are open/Ready for review; no `main` changes or Pages deployment
  were made in this iteration.
- New `ops/bsd_archive_receipt.py` emits **redacted, non-executable**
  research evidence on a genuinely checked-out data branch. It validates
  vendor object structure *at the original capture timestamp*, then
  separately checks if the observation is current. An old but valid archive
  returns `BSD_STALE_OPTIONAL_HOLD`, never fresh research or bookmaker odds.
- `ops/bsd_archive_reader.py` now allows an **empty, otherwise genuine**
  archive checkout lacking the optional `sources` directory. Both BSD
  latest files are classified as `MISSING_OPTIONAL`, rather than breaking
  the primary iPhone Pages build. Symlink/non-directory and invalid root
  are still rejected.
- New fail-closed tests cover: absent optional source directory, a file
  replacing the source directory, historical stale valid snapshot, future
  capture, exact matching/nonmatching research pair, and duplicate JSON keys.
  Real-world API, credentials, licensed market data and live betting remain
  untouched.
- [Read-only GitHub Actions canary #41585823368](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/41585823368)
  actually checked out the **mutable** `archive/bsd-free-research-v1` at
  `848eedb112cd26a850df23a7a9a90cf84129f706`; returned
  `NO_COMPARABLE_MARKET`, market_count 0 and an explicit `HOLD` with
  `production_recommendations=DISABLED`. No collector writes, Pages
  deployment, provider calls or paid market access occurred.
- On latest *code* head `183573130f87b79143bebf708fa849e5b323cef2`:
  **7/7 GitHub CI workflows successful**,
  **20/20 BSD targeted tests**, **2318/2318 ops tests**,
  **117/117 original V4.1 tests**. This documentation update requires
  its own PR-head CI before being called exact-head green.

**Remaining mandatory approval gates:** authorized independent reviewer,
a bounded **real** BSD archive writer canary (including archive/main commit
comparison), actual iPhone Pages read-after-write and rollback demonstration,
then other main writers and GitHub branch protection. No stage of this audit
certifies `verified_ev` or authorizes live betting.

## Required post-review acceptance (NOT yet performed)

- [ ] Distinct authorized reviewer approves exact workflow/script changes.
- [ ] All changed-file PR CI succeeds on the exact head, including new tests,
      the full ops regression and original V4.1 suite.
- [ ] Read back branch `archive/bsd-free-research-v1` and establish
      reasonable permissions/ownership for the public data (branch remains
      mutable; do not claim tamperproof custody).
- [ ] During an **authorized bounded** BSD workflow canary, confirm archive
      history/status commits appear ONLY on the archive branch; confirm main
      does not acquire a new BSD snapshot commit. Ensure no raw bookmaker
      quotes/API credentials entered Git history or Pages.
- [ ] Verify the subsequent `workflow_run`-triggered Pages job refreshes
      `bsd_backup.json` using the archive checkout, never stale main
      content; inspect UTC time, source status, optional HOLD, dashboard
      consistency and artifact logs.
- [ ] Verify retry/failure behavior: missing archive branch fails closed;
      invalid snapshot/symlink yields failure/HOLD, never primary-model or
      betting promotion. No new consumer write privileges.
- [ ] Before rollback to main-backed BSD snapshots, reconcile archive latest
      against main with the existing time-order guard; never replace a
      newer verified snapshot with an old one. Prefer disabling the optional
      overlay to HOLD during any uncertainty. Preserve history.
- [ ] After this one pair is accepted, continue inventory of all other
      main-writing collectors before activating mandatory main protection.
      This PR alone does **not** make main protection safe.

## Explicit limits

- No real provider canary was run as part of this Draft PR.
- A green CI is **synthetic engineering evidence** only.
- GitHub archive branch is still mutable and does not independently witness
  publisher identity, quotation time, kickoff or original model forecasts.
- Maintain `HOLD`, `certified_independent_forward_samples=0` and
  `production_recommendations=DISABLED`. Do not merge or enable betting
  merely because the publisher/reader pair works.

Tracking: [Issue #56](https://github.com/CHANCHUNWA1989/football-king-report/issues/56),
[PR #381](https://github.com/CHANCHUNWA1989/football-king-report/pull/381).
