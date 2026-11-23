# P0 #569 — six mutable source/latest reader compatibility and research-age gate

**2026-11-24 HKT · PR #571 Draft · offline research, HOLD / DISABLED.**

## Why this exists

A pinned real GitHub read-only comparison of archive bootstrap `3ce493fbeb9bfea29af1b93064a085afe8efb280` versus `main` `74913afd8ad92e49b05f2832a2d05e33781abd01` found **13 later main commits, 20 added history/provenance paths and six updated mutable source pointers**. Existing default-branch publishers and iPhone/Pages readers still have NOT migrated to an isolated storage contract. A copied latest file may be recent but incomplete, legally unlicensed for redistribution, stale as an actual bookmaker quote, or different from the historical snapshot.

## Six source read contracts inspected at pinned main SHA

| Pointer | Expected schema | Timestamp | Existing source status | Proposed bounded RESEARCH-age review budget |
|---|---|---|---|---|
| `sources/hkjc_tipsme_free_latest.json` | `football-king-hkjc-tipsme-free-research-v1` | `captured_utc` | `NOT_CONFIGURED`; third-party, not official HKJC API, `can_execute_bet=false` | 48 h |
| `sources/latest.json` | `football-king-extra-source-audit-v1` | `collected_utc` | `RESEARCH_ONLY`; independent final-score verification false, market fallback false | 12 h |
| `sources/live_germany_latest.json` | `football-king-openligadb-hourly-v1` | `collected_utc` | `RESEARCH_ONLY`; community source, no official second-by-second live guarantee | 3 h |
| `sources/seven_quality_gates_latest.json` | `football-king-seven-evidence-gates-v1` | `captured_utc` | `HOLD`; cannot promote model or recommend bets | 48 h |
| `sources/six_league_fixture_overlap_latest.json` | `football-king-six-league-two-publisher-fixtures-v1` | `captured_utc` | `HOLD`; market and secondary freshness false, independent results zero | 48 h |
| `sources/six_league_free_latest.json` | `football-king-six-free-league-quality-v1` | `captured_utc` | `RESEARCH_ONLY`; not executable prices and no verified OOS edge | 48 h |

The three six-league documents must carry exactly the **same** `captured_utc` before a candidate can be compared. This is a synchronized **report bundle**, not independent three-source agreement. Schedules observed in the actual workflows are hourly for Germany, three times daily for secondary, daily for the six-league triple, and daily for HKJC third-party research. The budgets in the table are **cautious proposed review ceilings**, NOT operator-approved SLAs, proof that a quote is tradable, or a release decision. Individual source market samples must be independently time-validated using their own quotation timestamps, licensing and two-source proof.

## New code delivered in Draft research branch only

- `ops/six_latest_reader_preflight.py` reads **exactly six allowlisted local paths** from each candidate and baseline snapshot, rejects missing or symlinked JSON, oversize files, duplicate JSON keys, NaN, mismatched schemas or safety flags, naive/non-UTC timestamps, clock rollback and future-dated sources. It also rejects unknown root statuses other than `RESEARCH_ONLY`, `HOLD`, or `NOT_CONFIGURED`, candidate age beyond the source-specific **research review** budget, and a split six-league timestamp. Raw bytes are SHA-256 fingerprinted without writing them or opening a remote Git connection. It does **not** fall back to `main`, guess a missing source, alter Git refs, call a feed, or publish an iPhone report.
- `ops/tests/test_six_latest_reader_preflight.py` now contains **16 synthetic local-file tests** covering a valid yet HOLD read contract, changed bytes at same timestamp, missing/mismatched files, promotion flags, stale/clock rollback/future-dated source, synchronized six-league bundle, duplicate key/NaN/invalid timezone, symlinks, rejection of unknown promotion-like status strings, and the always-nonzero CLI.
- CLI: `python -m ops.six_latest_reader_preflight --baseline-root <local-baseline-directory> --candidate-root <local-candidate-directory> --now-utc 2026-11-23T16:27:00+00:00` (example time is fixed for deterministic review, not the live clock). **A successful local parse still exits code 1**, prints `HOLD_SIX_LATEST_RESEARCH_READ_PREFLIGHT_ONLY`, `mobile_consumer_cutover_authorized=false`, `historical_blob_retention_verified=false`, `tradable_market_freshness_verified=false` and `production_recommendations=DISABLED`.

## GitHub CI evidence on code commit

On exact code SHA `5692573b075dba93ba956607e13208b5f22abf8d`:
- [Safety regression #45221622076](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45221622076), raw job `137857107176`: **15/15 new tests PASS; 2,553 Ops tests and 117 V4.1 tests** completed successfully.
- [Failover #45221622166](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45221622166), [Repository Safety #45221622094](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45221622094), [Offline 1X2 #45221622646](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45221622646), [Unified Ledger #45221622121](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45221622121), [Archive Bootstrap Readonly #45221622155](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45221622155): SUCCESS.
- **6/6 workflows on exact code SHA.** The tool was tested on **synthetic local snapshots**, not all original historical GitHub bytes or an authorized hosting cutover. Record the later documentation HEAD CI independently.

## Hard outstanding gates and owner actions

1. **All 20 added immutable historical/provenance Git blobs** need independently reviewed byte-level retention before routing producers to a new store. Six latest/status files are mutable and MUST NOT be misclassified as immutable proof; snapshots must be source/run/timestamp matched without a silent fallback.
2. Run the six-pointer preflight against separately prepared **pinned real checkout snapshots** only in a future approved offline review, accounting for producer cadence; also validate exact iPhone/Pages consumer schemas, unavailable states, latest age, and the same canonical settlement source for official-readiness and daily scorecard.
3. Public `main` is still `protected:false`; repository Rulesets were `[]`; independent PR reviews **0**. Hosted archive actor access and non-force/non-delete rules are not attested. Existing four direct-main Git pushes and 14 Contents API mutation-indicator workflow files remain unmigrated.
4. A nonauthor reviewer and owner/admin must approve effective isolated storage policy and deny a writer permission to `main` before any synthetic hosted write canary. **No** credential, remote writes, source rights assumption, bookmaker quotes or genuine positive EV are authorized by this preflight.

**Always HOLD / DISABLED. Leave PR #571 Draft and issues #569 / #439 / #452 open.**

## Subsequent status-denial hardening

A later research-only change rejects an unknown/promotion-like `status` (e.g. `READY_FOR_PRODUCTION`) even if the top-level `production_recommendations` remains `DISABLED`. The 16th synthetic fixture test explicitly verifies rejection. This is a preflight shape guard, **not** a policy that authorizes any verified market, player, data feed or production transition. The original 15-test CI receipt above belongs to the exact pinned earlier code SHA, not automatically to any later SHA; see the final PR check-run evidence for the later commit.
