# 足球王者 V：低額度 Codex 自主開發路線圖（研究模式）

Scope: Draft PR #451, branch `research/issue-450-asian-settlement`. This is a plan and a Codex handoff contract, **not an activated scheduler or an autonomous Codex session**.

## Goal and hard limits
Goal: move from research-grade pipelines to independently validated, reviewable pre-match recommendations. Code completion alone does not establish a predictive edge. No automatic betting, stake sizing, merge, deployment, paid API, or enabling recommendation flags. Keep HOLD/DISABLED until independent evidence and explicit human approval. The project may never qualify if prospective evidence does not support an edge.

## One-writer agent allocation
- Coordinator (logical role): read current branch, AGENTS.md, this plan, latest CI, and handoff; choose the next unblocked task; keep 8-line status.
- Codex Implementer (one active writer): minimal code/test changes for the chosen task.
- Data reviewer (only when source provenance or license is a blocker): verify provider rights, source identities and per-quote timestamps.
- Quant reviewer (only when independently verified prospective data is available): evaluate calibrated probabilities, market baseline, uncertainty and out-of-sample evidence.
- Security/release reviewer (once at phase gates): review leakage, safety and release requirements. Prefer GitHub Actions for repeatable tests, not an always-running agent.

No agent-to-agent discussions without a concrete blocker. At most one writer and one brief independent review at a gate. No duplicated code modules or repetitive full-repository audits.

## Sequential phase gates (stop when blocked)
| Phase | Work | Acceptance | Stop/block |
|---|---|---|---|
| 0. Reuse inventory | Read exact-head CI, changed files, current tests and real schema of market/latest.json; reproduce only confirmed gaps | Existing modules reused; focused failing test or documented no-op | If no confirmed defect, skip coding |
| 1. Capture | Connect existing pre-match forecast capture to authorized bookmaker snapshots; preserve raw bytes, SHA256, event identity and UTC capture times | Synthetic + negative tests, fail-closed, no backfill | No licensed provider or real quotes: stop integration, keep adapter |
| 2. Independent results | Preserve independent final score source, provider event ID and timestamp; reconcile to forecast event | Mismatch, stale and missing-source cases rejected | No independently verified results: stop |
| 3. Evaluation | Prospective chronological holdout, coverage, exclusions, calibration, Brier/log loss vs same-time market baseline; bootstrap/time-block uncertainty | Reproducible report, source hashes, no leakage | Too few or unverified samples: collect shadow data, no edge claim |
| 4. EV research | Use actual executable odds and validated settlement for each market; assess fees/limits/staleness, sample size, intervals and CLV where available | Independent reviewer confirms evidence quality and whether any positive EV is supported | Negative/uncertain advantage: remain research-only |
| 5. Release review | Security, data rights, reliability, auditability and human approval | Explicit signoff after all gates; no automatic release | HOLD/DISABLED remains default |

## Codex minimal loop
1. Read `AGENTS.md`, this plan, and `docs/codex-low-cost-handoff.md`; check `git status --short` and exact-head CI.
2. Pick the **first unblocked** gate; inspect only files it owns and their tests. Do not reopen completed work.
3. Add a regression test for a confirmed defect; fix with minimal diff. If no defect, write no code.
4. Run focused tests first; run `python -m compileall -q ops` and `python -m unittest discover -s ops/tests -q` once at the gate boundary; rely on GitHub Actions for full CI.
5. Commit only on the research branch; leave PR Draft. Stop on external license, missing API access, unverified results or insufficient sample. Do not repeatedly retry.
6. Update handoff in at most eight lines and stop. Next session reads handoff instead of the whole repository.

## Completion is evidence-gated, not time-gated
The 77 archived 1X2 rows are not independently result-verified and have no executable Asian odds. Their model Brier/log loss underperform the market baseline in the existing audit. Never transform them into verified EV, ROI, or Asian market evidence. Formal recommendation is an explicit separate decision; never auto-enable merely because all tests pass.

## Minimal reusable Codex prompt
Read AGENTS.md, docs/codex-low-cost-roadmap.md and docs/codex-low-cost-handoff.md. Work as the sole coding agent on PR #451. Choose the first unblocked gate, reuse existing modules, make the smallest tested change or no-op, run focused tests, update handoff (<=8 lines), and stop. No paid API, new agents, automatic merge/deploy, or activation of HOLD/DISABLED.
