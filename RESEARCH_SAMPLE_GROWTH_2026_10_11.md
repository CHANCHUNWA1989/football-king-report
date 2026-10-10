# 足球王者｜增加真正前瞻研究樣本（2026-10-11）

## Situation

The current public evidence ledger contains six settled research pairs, but they
are **not independently verified**. The promotion gate requires at least 300
unique point-in-time settled model/market comparisons, 12 independent calendar
week blocks, and at least 40 samples in four separate leagues. Further
independent scores, calibration, executable quotes, market-relative out-of-sample
performance and manual review are also required. Hitting 300 is not automatic
betting authorisation.

## What changed without new API calls

Previously the free no-key TheSportsDB collector spent its six daily-date slots
per league on today and five future days. It also requested one previous match
per league. There was no dated multi-match historical coverage to help verify
multiple recently completed fixtures.

The six date offsets are now: `0, -1, +1, -2, +2, +3` UTC days.
For each of the six target leagues this retains:
- 1 next-league request
- 1 previous-league request
- 6 date queries (4 near-term calendar slots, 2 finished-match lookbacks)

**Total remains 48 free requests per full collection**, at the established
pacing. Requests are rotated across leagues; the collector still stops on 429.
Future fixture lookahead is reduced from five days after today to three. No
private keys, quote bodies or paid Odds API credits are used.

The existing independent-score auditor may now see more recent FINISHED
results. These are **candidate publisher observations only**, not newly
verified samples; scoring a sample still requires a genuine earlier archived
forecast, earlier market, correct fixture identity, credible final score and
existing independent-provenance policy. Extra matches without that evidence
must not be counted.

The new `recent_final_score_observations` count is reconciled against archived
sanitised rows by the publication guard, not trusted as a provider claim.
The `six_league_independent_results_verified` flag remains false and
`production_recommendations` remains `DISABLED`.

## Real sample collection process

1. Keep automated pre-kickoff Shadow forecasts and research-only market
   snapshot archival running, recording point-in-time timestamps.
2. Use the quota-safe collector to obtain recently finished source-score
   candidates; retain both winning and losing forecasts.
3. Only settle distinct, unambiguous archived pre-kickoff model/market pairs
   after real full-time results.
4. Require independent agreement of exact final scores before claiming a
   result as independently verified.
5. Monitor count by league and week, incomplete market matches, API coverage
   and market-vs-model log loss; do not backfill old results as if predicted.
6. Retain at least 300 valid forward samples over 12 calendar weeks, then
   re-evaluate all other promotion conditions. Success is never guaranteed.

## Verification

Run the full zero-network unit suite and free-source publication guard tests.
Monitor the two existing daily optional-source collector runs and mobile report
jobs via GitHub Actions. The first real run after deployment determines whether
more completed fixture observations were actually captured. Do not report a
sample increase until the archived evidence ledger confirms it.
