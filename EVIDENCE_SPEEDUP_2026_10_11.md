# 足球王者｜加速真實證據轉化（2026-10-11）

## Problem verified

The 2026-10-11 public report held six already settled prospective shadow
comparisons, but **zero independently attested final results**, with only
one of seven existing evidence gates passed. A successfully archived free
fixture collection was not guaranteed to trigger an iPhone research refresh
because commits made with `GITHUB_TOKEN` do not normally emit follow-on
`push` Action runs. Reports could therefore remain stale for up to the next
six-hour daily-report schedule.

## Release improvements

1. Subscribe the trusted iPhone reporting workflow to successful completions
   of the existing four-free-source collector and the scheduled The Odds API
   research archive. The workflow runs only after the whole upstream workflow
   succeeds, not merely after a partial collection. No new provider calls or
   bookmaker API credits are created by the trigger itself; extra iPhone
   renders can consume GitHub Actions minutes.
2. The existing **OpenLigaDB** and **OpenFootball** Bundesliga crosscheck
   now preserves a bounded list of identical full-time score candidates, in
   addition to its original aggregate quality warnings and conflict gate.
3. Match these candidate observations against **existing** immutable
   settled research outcomes, league-scoped identity and nearby kickoff
   dates. Duplicate or ambiguous fixtures, conflicting outcomes, stale,
   untrusted, malformed, or unsafe crosscheck documents fail closed.
4. Show cross-publisher correlated Bundesliga outcomes in
   `independent_results.json` and `evidence_progress.json` **under separate
   explicitly research-only counters**, without upgrading the independently
   attested result count, modifying the old settled ledger or relaxing
   production qualification.

## Why this is not an immediate official recommendation

Score agreements are published observations, not cryptographically attested
independence, not executable prices, and not evidence of profit. Even if
correlation counts rise, there are still only the genuinely archived and
settled forward fixtures and no new historical predictions can be created
after kickoff. The release keeps `production_recommendations=DISABLED`.
The existing minimums of 300 distinct point-in-time settled comparisons, 12
week blocks and 40 observations per league in at least four leagues must still
be satisfied alongside benchmark outperformance, executable price evidence,
source provenance, independent review, and manual promotion.

## Verification

Run `python -m unittest discover -s ops/tests -q` and all CI and stress jobs.
Inspect automatic actions for post-collector iPhone rebuilds, inspect actual
`independent_results.json` for `bundesliga_two_publisher_candidate_audit`,
and never count raw score candidates as newly sealed samples.

Watch-outs:
- GitHub `workflow_run` can queue additional iPhone reports; concurrency is
  preserved and `cancel-in-progress: false` to avoid interrupting archives.
- If the provider feed fails or the cached crosscheck is stale, output HOLD
  for correlation rather than producing a fabricated positive result.
- Never equate different publisher domain labels with source independence
  certified for real-money betting.

