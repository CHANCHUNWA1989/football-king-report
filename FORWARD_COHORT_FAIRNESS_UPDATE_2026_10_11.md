# Football King | Prospective cohort and A/B/C/market fairness audit

**Registered 2026-10-11. Research and source diagnostics only, never a betting model promotion.**

## Real bottleneck observed
The repository's forward ledger initially has seven unverified settled
fixtures, all Bundesliga, while four leagues must each reach 40 samples and
there must be at least 300 independent pre-match settlements across 12
different calendar week blocks. The newly preregistered market-anchored
challenger C has no legitimately settled forecast yet. A small single-league
score improvement is not proof of reliable performance.

## New six-league archived-pair backlog audit

`ops/forward_cohort_backlog.py` reads the **existing immutable**
`research_pairs` archives, the same run's strict settlement ledger, current
public fixture report and the same runner-local finished observations. It
uses the **same** time and league-specific match rules as the original
forward settlement engine; it requests **zero** new APIs.

A sealed unique archived pair is classified as:
- already in the unverified settled research ledger;
- kickoff / two-hour finality buffer not yet elapsed;
- final-score observation missing or cannot match fixture/kickoff identity;
- multiple ambiguous finished score matches;
- exactly one source final was observed but the settlement ledger hasn't
  incorporated it (diagnostic of a potential ingest defect, NOT permission
  to add a result manually).

This makes the real bottleneck by league visible. The report also shows:
sealed pairs per league, C and jointly sealed A/B/C/market pairs, sealed C
settlements, true four-way settled cases, 40-per-league shortfalls and the
remaining 300-sample gap. These counts do **not** claim independently
authenticated match results or future win rates. The public site publishes
`forward_cohort_backlog.json` and a human-readable source backlog table.

Untrusted/duplicate existing evidence, tampered timestamps, and unsafe
provenance produce a hard failure rather than inflated counts. The command is
read-only with respect to archive and ledger.

## Fair simultaneous four-way research audit

Before this change A/B experiments and newly introduced C could be
compared on *different* finished fixtures. Such a comparison can create
spurious changes when league strength or match outcomes differ.

`research_center.json` now exposes
`prospective_four_way_research` on **only the same results containing
verifiably sealed original A, fixed-shrink B, newly registered market-anchored
C and prior-market baseline**, with matched n and ISO week coverage. Log Loss
and multiclass Brier are computed on the *identical outcomes*.

Additional provenance hardening checks that any stored B genuinely equals
the preregistered 15% probability shrink formula. Previously a syntactically
valid vector labeled as B could pass ledger merge even if its values had
been replaced. The archive scanner, old-ledger validation, cumulative
evidence merge and four-way score audit now refuse such tampering. Older
records **without** B or C remain baseline-only; they are not filled in
after the result or silently included in the four-way denominator.

## Promotion status unchanged

All outputs preserve `production_recommendations=DISABLED`. No amounts,
raw bookmaker quotes, implied execution prices, ROI, or artificial model
probabilities are published. The real sample threshold, independent source
certification, week/league spread, calibration and market advantage still
require genuine forward results and explicit manual review. The project
must not turn a green GitHub Action into a betting recommendation.

## Validate

Run the full GitHub unit, stress, regression and iPhone publication suites.
Unit tests cover the six backlog states, stale/mismatched and contradictory
results, bad ledgers and duplicate archived pairs, HTML/JSON safety, tampered
B rejection, and the A/B/C/market same-fixture performance denominator.
After merge, inspect the Actions run and the published
`forward_cohort_backlog.json`. Distinguish newly *archived* pairs from truly
settled and **independently verified** cases.
