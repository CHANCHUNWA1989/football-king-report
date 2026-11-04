# Evidence audit V2 — research-only upgrade proposal

Status: PROPOSAL / SHADOW MODE. Production recommendations: DISABLED.

## P0 evidence gates
- Retain immutable forecast and market snapshot hashes and timestamps before kickoff.
- Independent result verification: two genuinely independent upstream providers, with captured UTC times, provenance, and conflict quarantine.
- Reject future-dated, stale, post-kickoff, missing or mismatched records. Never rewrite archived predictions.
- Record all published selections, withdrawals, reversals and superseding versions as append-only events.
- Keep unverified settlements separate from verified evaluation datasets.

## P1 evaluation
- Compare A, B, C and contemporaneous de-vig market on *identical* match sets and pre-kickoff cutoffs.
- Report multiclass log loss and Brier score with sample counts, confidence intervals, league/time strata, reliability diagrams, and home-win probability calibration.
- Include baselines, paired per-match score differences, block bootstrap by matchday/week and sensitivity to data exclusions.
- Mark C as unavailable until forward-logged samples exist; never infer profitability from scoring rules.
- Do not claim improvement without preregistered out-of-sample evidence.

## P2 operations
- Run daily in Asia/Hong_Kong, display both report cutoff and source snapshot timestamps.
- CI gates: schema checks, monotonic timestamps, no-lookahead, idempotency, immutable archive checks, independent-result provenance and no automatic merge.
- On API exhaustion, degrade to 'insufficient evidence', not fabricated odds.
- Require human review for provider disagreements, withdrawals/reversals, CI failures, and any proposed model promotion.

## Acceptance criteria
- All P0 checks green; independently verified outcomes available.
- At least 300 prospective verified fixtures over >=12 distinct weekly blocks before promotion review (minimum planning threshold, not statistical guarantee).
- Production recommendation flag stays DISABLED; human approval required for all code merges and releases.

Baseline observed 2026-10-14 06:07 HKT: 28 settled research labels, 0 independently verified; A and B trail de-vig market on matched samples. This proposal does not alter historical evidence.
