# PR #460 — Per-fixture A/challenger/market snapshot alignment gate (research)

2026-11-15. **DRAFT / HOLD / DISABLED; main unchanged.**

## Problem in previous comparator

`ops/paired_challenger_comparison.py` computes retrospective
`unverified_diagnostic_metrics` from one combined row containing
`as_of_utc` and three 1X2 vectors. That row alone cannot establish
that the original A forecast, Penaltyblog challenger and market comparator
had their respective snapshots **available at the same decision cutoff**.
It also does not store distinct model production times, last input times
or a market quote receipt time. A self-reported `independently_verified`
boolean never constitutes external provenance.

This new gate does **not** overwrite the existing comparator or relabel
historical archive rows. It offers a stricter optional intake before any
future research comparison.

## New isolated code

- `ops/paired_snapshot_alignment_gate.py`: original, standard-library
  offline function `audit_aligned(payload)` and read-only CLI.
- `ops/tests/test_paired_snapshot_alignment_gate.py`: synthetic
  positive/negative tests, not external verification.
- `.github/workflows/paired-challenger-comparison.yml`: add dedicated test
  step and path filters (do not modify main/prod workflows).

`football-king-paired-snapshot-alignment-v1` JSON object contains exact
top-level keys: `schema`, `production_recommendations="DISABLED"`,
`fixtures`, `model_a`, `challenger`, `market`.
Every fixture has:

`source_namespace, fixture_id, league_id, home_team_id, away_team_id,
kickoff_utc, as_of_utc, result_received_utc, outcome`.

Here `outcome` is the integer 0 (home), 1 (draw) or 2 (away).
Both model lists must cover exactly those fixture IDs, retaining all
identity and cutoff keys, plus `produced_utc, max_input_received_utc,
probabilities`. The market list must cover the exact same native IDs and
cutoffs and provide `quote_received_utc, bookmaker_id, market_type="1X2",
probabilities`. Each `probabilities` is **three 1X2 probabilities,
not bookmaker odds**. Reported market probabilities are only
caller-generated comparative baselines, not executable tradable quotes.

Use, from repository root, only with locally available lawful and
explicitly **unverified** research summaries:

```sh
python -m ops.paired_snapshot_alignment_gate --input /private/research/paired.json
python -m unittest discover -s ops/tests -p test_paired_snapshot_alignment_gate.py -v
```

No automatic Penaltyblog installation, third-party scraping, licensed data
download, site publication, bookmaker actions, model refit or output file
write occurs in this module.

### Local fail-closed requirements

1. **Exact canonical native IDs:** same `(source_namespace,fixture_id)`,
   league, team IDs, home/away orientation and UTC kickoff across all four
   lists. No fuzzy names or silently skipped missing fixtures.
2. **One per-fixture cutoff:** all three streams' `as_of_utc` timestamps
   must equal the fixture's declared decision cutoff after UTC conversion.
   No post-kickoff cutoffs. All declared times must be timezone-aware.
3. **Input chronology:** last source input no later than model production,
   which must be no later than cutoff; market quote received no later
   than cutoff **and no later than the earlier of two model productions**.
4. **Staleness:** both produced model snapshots and market quote no older
   than 120 minutes at the declared cutoff; no user-supplied flag changes
   this threshold.
5. **Result chronology:** result must be declared received at least 90
   minutes after scheduled kickoff. This is necessary but does *not*
   authenticate the actual result, stoppage time or match identity.
6. **Cohort atomicity:** missing, duplicate, swapped, nonfinite, malformed
   or injected certification fields cause entire input to HOLD without
   any `unverified_diagnostic_metrics`.

When schema/chronology pass, the tool outputs only **unverified descriptive**
paired accuracy/Brier/log loss, 0 certified prospective samples and
`status=HOLD`. A valid local transcript is not a valid or signed event
source.

## Not yet satisfied

- **No genuinely matched external source A and Penaltyblog forecasts**
  with publisher-authenticated capture, independently witnessed
  pre-kickoff time, verified training data and exact complete version
  histories are available in this PR. The new test cohort is synthetic.
- No independent match-result source origin, score truth verification,
  rights scope clearance, accessible market executable quote/limit or
  independent locked pre-match data. No claim of EV, ROI or improved model
  skill from this gate.
- External software package licenses do not authorize scrape/data use
  in commercial prediction/wagering. Original upstream source code has
  not been copied.
- GitHub `main` branch protection, eligible genuinely independent
  reviews and signed forecast producer remain release blockers; see
  [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439).

PR #460 must stay **OPEN/DRAFT/UNMERGED** with
`production_recommendations=DISABLED`,
`positive_ev_verified=false`, `certified_prospective_samples=0`.
Do not treat a green CI as source/signature or statistical proof.
