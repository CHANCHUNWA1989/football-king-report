# Intelligence-X P28 release qualification review — HOLD
Review: 2026-11-25 HKT. Scope: exact football PR #604 head 38a0463c8e139f33a1ccc3b1341b38a68d7a488a and quant PR #52 head 5ebb71940476bb5fb3c8e9d9abf707ad3e160b4a. Both draft, unmerged at review. This is an evidence inventory, not independent sign-off or release authorization.

## Evidence checked
- Football PR #604: https://github.com/CHANCHUNWA1989/football-king-report/pull/604
- Five successful PR workflow runs on the reviewed head: 45444009513 (repository safety), 45444009943 (offline 1X2), 45444009618 (ledger), 45444010231 (regression/failover), 45444009690 (safety).
- Actual regression log: https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45444010231/job/138622641885 — 2517 tests in 24.250s, OK (skipped=16). 2501 non-skipped; not a match-accuracy count.
- Quant PR #52: https://github.com/CHANCHUNWA1989/global-quant-ai/pull/52 — five failed workflows, runs 45388654969, 45388654816, 45388654897, 45388655264, 45388654825. Investigation #53 remains unresolved; no new failure diagnosis in this review.
- Read exact-head ops/evidence_readiness_inventory.py, ops/recommendation_readiness_gate.py, ops/trusted_result_evidence.py, research/intelligence_x/n8n_rehearsal_guard.json. Inventory explicitly hardcodes authenticated independent settlement count to 0 and requires 300; this is a pipeline limitation, not an inventory of all real results. Readiness checklist booleans are metadata only and cannot activate production. Trusted result evidence has no promotion path; n8n workflow is inactive.

## Historical diagnostic (existing report, not newly rerun)
Source: research_reports/retrospective_error_diagnostics_2026_10_26.json, Git blob 31f474fb269551338cf08778d59c04ab9836ecba. Report dated 2026-10-26, pinned OpenFootball archive e6744429ee395bc86f247348c6184bb08d4eb361. Development 2024-25; previously inspected 2025-26 date-only retrospective holdout: 2118 cases, 35 calendar weeks.

| Model | Top-choice hit rate | Log loss | Three-class Brier |
|---|---:|---:|---:|
| Original Poisson shrinkage v4.1 | 47.21% | 1.04157 | 0.62660 |
| Draw adjustment | 47.12% | 1.04121 | 0.62642 |
| League-frequency baseline | 42.92% | 1.08130 | 0.65438 |

Original: 1000/2118 correct, Wilson 95% interval 45.10–49.34%; draws 4/555 correct (0.72% recall). Draw-adjustment gain over original paired-week 95% intervals: hit-rate [-0.00626, 0.00386], log-loss gain [-0.00274, 0.00353]; neither establishes improvement. No authentic kickoff timestamps, prospective forecasts, independently authenticated results, market baseline, or ROI estimates. Do not promote a model using this previously inspected cohort. No new backtest performed.

## Release decisions and acceptance conditions
| Area | Status | Next independently verifiable acceptance |
|---|---|---|
| Football offline research | RESEARCH_ONLY | Exact-head CI and review; preserve skips and failures; no production switch |
| Source rights and identity | BLOCKED | Scoped rights review and independent origin evidence, fixture/team mapping, official cards, preserved upstream timestamps and raw evidence |
| Prospective evaluation | BLOCKED | Authentic prematch sealed forecast linked to independently authenticated actual kickoff/result; existing minimum 300 admitted settlements, not an automatic guarantee of skill; preregister paired comparisons and calibration checks before new holdout |
| Model quality | BLOCKED | Fresh prospective sample; log loss/Brier, calibration, per-outcome recall, paired uncertainty; assess market baseline only with authentic timestamped quotes |
| Persistent safety | BLOCKED | Durable independent witness, compulsory gate migration, crash/power-loss and lease revocation evidence |
| Automation | BLOCKED | Actual restricted n8n runtime, controlled shadow execution, scheduler, outage and alert-delivery tests; proposed minimum 24h observed rehearsal before longer acceptance |
| Finance | BLOCKED | Resolve CI runner/startup failure, all original workflows with real runner steps/logs pass; no orders or live execution |
| Production release | DENIED | Independent human approval only after all relevant evidence is satisfied; no automatic promotion |

Priority: repair actual evidence admission and source qualification, rather than adding numbered wrappers. Keep a separate read-only offline research lane. Do not count historical replay or unverified source agreement as prospective settlements. Do not change main, activate schedules, subscribe, deploy, or trade in this review. All formal recommendations remain DISABLED; status HOLD. P27 full prospective and runtime acceptance remains incomplete. P28 review performed, release not approved.
