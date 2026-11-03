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
