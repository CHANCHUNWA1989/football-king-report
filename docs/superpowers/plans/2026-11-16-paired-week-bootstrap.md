# Paired UTC-week bootstrap implementation plan

> For agentic workers: use superpowers:executing-plans; one implementer, one bounded research increment.

**Goal:** Add a weekly cluster sensitivity interval to the existing paired Poisson/DC research assessment.
**Architecture:** Reuse validated per-fixture differences, UTC timestamps, seeded random sampling and percentile calculation in `ops/penaltyblog_paired_uncertainty.py`. Forward the added fields through the existing pipeline; preserve original IID output exactly.
**Tech stack:** Python standard library, unittest, existing optional model integration.
**Spec:** `docs/paired-refit-uncertainty-research.md` describes the current IID limitation; the rules below are this increment's predeclared engineering policy, not statistical-power certification.

## Global constraints

- Keep Draft #458, HOLD/DISABLED, positive EV=False; no merge/deployment, provider access, real-data scoring or sealed record changes.
- Group by ISO year/week of UTC kickoff; both models and every metric share each whole-week resample. Weeks are sampled with replacement, uniformly, with the original number of weeks per draw.
- Divide each draw's summed fixture differences by that draw's actual fixture count; do not average week means. Sort week keys and reuse the existing metric quantile function.
- Require >=30 fixtures AND >=12 observed UTC weeks. These are research reporting floors, not authenticated independent clusters, formal inference or an advantage/promotion criterion.
- Use a separate `random.Random(seed)` stream so existing IID values do not change. Retain bootstrap repeats/seed validation and all source, identity, cutoff and chronology gates.
- Add `week_block_count`, `week_block_interval_status`, `week_block_bootstrap_repeats`, `paired_week_block_bootstrap_95pct_intervals`. Insufficient data returns no weekly interval and zero weekly repeats.

## Review focus

- Unequal week sizes: preserve fixture weighting in each resample.
- Timezone and ISO-year boundaries: group by actual UTC instant, not timestamp spelling or calendar year alone.
- Many matches in one week: no weekly interval even when the IID floor is met.
- Invalid/missing/cross-cutoff forecasts: no partial weekly counts or intervals.
- Correlated synthetic fixtures: verify a block sensitivity interval differs from IID; never claim real profitability from the example.

## Task 1: one assessment/pipeline increment

**Files:** modify the existing uncertainty module, pipeline, their two tests, and research document; no new implementation module.
**Interfaces:** `assess(payload, *, bootstrap_repeats=1000, seed=42)` and `run_pipeline(...)` retain signatures and existing fields; expose the four added fields above.

- [x] Add failing tests for reporting floors, whole-week paired draws, unequal block sizes, UTC/ISO boundaries, determinism/input immutability, invalid cohorts and pipeline forwarding.
- [x] Run the affected tests and observe nine missing-field failure cases before implementation.
- [x] Compute weekly intervals from existing validated differences and forward the four fields. Update descriptive limitations; 61 related tests passed.
- [x] Run 61 related tests, full regression on updated base (2,886, zero failures, two optional-dependency skips), compileall and diff check; one read-only QA found no implementation defect. Strengthened repeated-block denominator coverage after QA; related tests remained green. Preserve upstream time-decay candidate through `5b27aa1a` without duplicating or modifying it.
- [ ] Update the existing document's handoff in <=8 lines, commit/push original branch, verify exact-head CI and update Draft PR. No merge/deployment.

Publishing/CI acceptance is recorded in the Draft PR body after the commit; this pre-commit checklist is not rewritten merely to trigger another CI run.
