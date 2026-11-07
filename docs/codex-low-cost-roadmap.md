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


## Codex autonomous execution contract (2026-11-06)

**State:** instructions only; this commit does NOT launch Codex, create a Codex scheduled task, connect MCP, provide billing credentials, or authorize production launch. ChatGPT's GitHub connector may edit this branch, but it cannot start a Codex session. Codex scheduled tasks are configured separately in the user's enabled Codex/desktop environment; noninteractive `codex exec` or an approved SDK/CI runner is an alternative.

### One-time Codex activation (user-controlled)
1. Open the actual Football King V repository in Codex using a trusted local **worktree** or a published cloud environment that includes the repo. Confirm the current research branch and exact-head checks. Prefer the desktop Scheduled task UI when available; otherwise run one bounded `codex exec` job from a separately approved scheduler.
2. Use the **one-time bootstrap prompt below** and choose a conservative schedule or manual trigger. Do not configure a repeating paid CI action, external tool, credential, broad write permission, or API key without explicit separate approval. Only the configured Codex runtime can confirm `codex mcp list`; ChatGPT-installed plugins do not confirm Codex connectivity.
3. Keep the computer and supported app running for local project scheduled tasks. A schedule wakes a task; it does not make missing vendor permissions or independent human approvals appear.
4. Already completed work is immutable evidence: A04 settlement guard, P0-5 provider evidence checklist, P0-7 provider outreach (both messages subsequently **sent and recorded in #452**), and one-line CI naming fix in PR #451 at `90feb17317f2db2f67b71a6ef980879b7eba50df`. Always check the **newest** SHA before doing anything.
5. The next live blockers are #452 (genuine licensed per-quote sportsbook odds, independently sealed prospective forecasts and FT90 outcome) and #439 (main branch rulesets and eligible independent human review). No source rights or proof of positive edge has been admitted.

### Bootstrap prompt: paste once into Codex

> You are the single low-quota coordinator/implementer for `CHANCHUNWA1989/football-king-report`, existing Draft PR #451 on `research/issue-450-asian-settlement`. First read `AGENTS.md`, `docs/codex-low-cost-handoff.md`, this roadmap and the exact HEAD/CI for #451. Respect the **research-specific** guard over any generic maintenance merge authorization. 
>
> Before every task, compare the current HEAD, already reported gate states (#439, #452) and any newly authenticated external data or GitHub findings to the last handoff. If nothing material changed or all remaining work requires an external licence/admin/human decision, output `BLOCKED_EXTERNAL / OWNER_ACTION_REQUIRED / NO_CHANGE` as appropriate and **STOP WITHOUT edits, tests or repeated provider queries**. Do not create dummy work or loop forever. 
>
> If and only if a truly **new, unblocked, independently testable** P0 issue exists: choose ONE issue; reuse existing modules; one writer, no default Data/Quant subagents; prove the failing case, make the smallest branch-only fix, run focused tests, run at most one complete local suite if warranted, and verify exact-head GitHub Actions. Up to two targeted corrections; if still failing, report and stop. Optional read-only QA once at the relevant gate only. Preserve original snapshots, logs, provenance and evidence. Do not print credentials.
>
> Update `docs/codex-low-cost-handoff.md` in at most eight lines with HEAD, evidence, focused/full tests, actual CI results, blockers and the next eligible task. Write Cantonese/Hong Kong Traditional Chinese summary. **Keep PR #451 Draft; never merge/deploy, use paid API, turn on betting or production recommendations, claim verified positive EV from synthetic results, or substitute AI review for the independent human #439 requirement.** Stop after one bounded task. The next scheduled invocation reads the handoff, not the entire repo.

### Deterministic zero-token-first allocation
- Local `git`, `rg`, focused Python tests and GitHub Actions first. An LLM is not necessary for checking whether a JSON value or CI status changed.
- GitHub reads, official documentation MCP/Context7, and Firecrawl only when the existing evidence cannot answer a **new** question. Confirm tools are configured in the **actual** Codex runtime before claiming they were used; these calls have their own costs/context overhead.
- New vendor mail is monitored by the **separate existing ChatGPT/Outlook task**. Never spawn another Codex poller for the same providers. An authenticated new provider response may authorize a narrow follow-up; a provider marketing page is not an authorization.
- Security admins set and verify the `main` ruleset and independent human review outside Codex. Codex may prepare safely reviewable branch-only diffs but may not self-certify approval.
- Never run back-to-back scheduled Codex sessions merely to return `HOLD`. Enable/resume the coding schedule only when an unblocked input exists; default to idle.
