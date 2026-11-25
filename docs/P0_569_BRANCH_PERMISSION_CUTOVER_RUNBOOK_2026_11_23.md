# P0 #569 / #439 — archive branch and writer permission cutover runbook

**Draft for independent OWNER and non-author REVIEWER approval · 2026-11-23 HKT · research-only, HOLD / DISABLED.**

> **NOT an instruction to execute automatically.** No remote branch, GitHub Ruleset, token, production workflow, credential or reader is modified by this file. No real bookmaker feed, soccer result, OOS profitability, or positive EV certified.

## 1. Exact evidence and governance blockers

Read-only observed repository state on 2026-11-23:
- Repository: `CHANCHUNWA1989/football-king-report`, default `main` SHA `3ce493fbeb9bfea29af1b93064a085afe8efb280`.
- `GET /repos/.../rulesets`: `[]` (no repository Rulesets returned).
- Detailed `GET /branches/main/protection`: **403 Resource not accessible by integration**. Do not infer settings from this inaccessible endpoint.
- Previous `GET /branches/main`: `protected:false`; do not claim require-PR or no-bypass in effect.
- Fixed proposed archive ref `refs/heads/research/forward-provenance-archive`: branch search returned **no match**. No official remote canary, custody or branch protection evidence exists.
- PR #571: Draft/open/unmerged with **0 independent reviews**.
- See `docs/P0_569_15_WORKFLOW_WRITE_TARGET_MATRIX_2026_11_23.md`: **15 workflows** have `contents: write`; **14** have Contents API mutation indicators; **four direct-main Git push job blocks in two workflows**. The history of five failed settlement PUT attempts lacks sanitized HTTP status evidence.

**Fail-closed decision today:** main no-bypass Ruleset activation **NOT AUTHORIZED**; archive producer cutover **NOT AUTHORIZED**; verified betting / source promotion **DISABLED**.

## 2. Permission and destination architecture proposed (not applied)

| Actor / program | Required minimum | Must not be able to do | Proposed storage / read contract |
|---|---|---|---|
| Read-only collectors and report builders | `contents: read`; `actions: read` only when strictly needed; Pages/OIDC per independent approval | Push Git refs, PUT contents, self-approve rules, invoke a write-capable reusable workflow | Signed/run-bound artifacts or source-readable *sanitized* research snapshots; no raw licensed feed in public repo |
| Provenance, NDR, OpenLiga capture append writers (four jobs) | Separate named, reviewed archive-writer identity; access only to pre-provisioned archive destination, with non-force append safeguards | Write to `main`, change workflow/Ruleset files, force-push, delete, rewrite same run ID, issue broad admin PAT | `refs/heads/research/forward-provenance-archive` or independently permission-isolated archive repository/object store; SHA-pinned read-back |
| Settlement cumulative writer | Same opt-in isolated proof writer discipline, complete legacy merge + collision rejection | Reset historical 105+ research rows, claim independent scores from saved flags, fall back to `main` on error | Append `settlement_batches/` and reconcile full verified legacy bytes for mobile |
| Source and market latest/status publishers (12 P0-B producers) | Independently bounded, reviewed *publish*-identity and explicit destination ref/API path | Continue implicit default-main Contents PUT, silently overwrite newer market snapshot, expose raw private feed | Separate immutable history and separately versioned mutable public latest manifest; readers explicitly select signed/pinned source and freshness |
| Weekly report publisher (P0-C) | Report artifact or approved PR for reports | Unreviewed Contents PUT to default main | Keep older report URLs, use approved publishing route |
| Governance administrator | Admin rights only for owner/admin step, outside Actions runtime | Store admin PAT in workflows, bot bypass, self-review, production promotion by CI green alone | Explicit Rulesets, approvals, required checks, source of policy proof and rollback evidence |
| Independent human reviewer | Read security diff, workflows, effective permissions, branch rules, data retention and consumer tests | Author self-approval or approving a stale, subsequently changed HEAD | Recorded non-author review and HEAD/CI correlation before any approved migration |

**Important:** A job-level `permissions: contents: write` grants a repository-scoped token capability; it is **not a branch-scoped credential**. Naming a target branch in `git push` or `gh api -f branch=...` is a code convention, NOT a security boundary. The owner must use independently enforced branch rules or an actually isolated archive repository/object store and verify the actor cannot push to `main`. Consider a separate repository/store when hard separation is essential. A `main` Ruleset with no bypass must not be activated before the remaining writers stop depending on direct-main updates.

## 3. Execution phases and stop/go gates

### Stage A — owner/reviewer inventory and freeze (READ ONLY)

- [ ] Obtain an independent nonauthor security reviewer; record exact identity, time, reviewed PR HEAD and approval, no self-approval.
- [ ] Confirm actual `main` SHA and current protected/ruleset state with authorized read/admin evidence, including bypass actor list; missing rights are a **HOLD**, not an assumed pass.
- [ ] Review all 63 workflow files and 15 write-capable producers, including scripts, reusable/composite actions, dynamic destinations, concurrency and actual permission scopes; classify all downstream Pages/mobile consumers.
- [ ] Establish per-producer source rights, redaction, byte-level history preservation, retention and removal policy. Any unknown source provenance holds the relevant pipeline.
- [ ] Record a clean immutable candidate code SHA, not just 'latest', and exact CI run IDs. Changes after review invalidate earlier approval.

### Stage B — independent archive infrastructure (OWNER ACTION, not auto-created)

- [ ] Select pre-provisioned fixed ref or independent repo/object store, actor identity, owner access and storage retention. Permit only approved *synthetic* canary bytes initially.
- [ ] Independently configure and read back archive protections: non-force writes, deletion/rewrite denial, actor restrictions, audit trail and rejection of unauthorized pushes. Do not assert GitHub-native branch-limited `GITHUB_TOKEN` scopes.
- [ ] Independently demonstrate the writer credential **cannot write `main`**; do not execute destructive experiments against real `main` or install admin PATs.
- [ ] Approve a scoped canary with one fixed branch/ref and an immutable baseline `main` SHA; avoid any workflow that runs ordinary source collectors during this step.

### Stage C — synthetic-only authorized remote canary (BLOCKED TODAY)

- [ ] Capture remote archive ref SHA, current `main` SHA, active protection rules and independently reviewed actor scope before writes.
- [ ] Run exactly one allowlisted 10-file synthetic proof and one synthetic settlement batch through the gated **official** writer entrypoints. No provider data, tokens, genuine odds or personal data in proof files.
- [ ] Replay same run identifiers and demand `ALREADY_ARCHIVED`, unchanged remote archive ref. Change one synthetic payload byte and require collision rejection; no force-push.
- [ ] Read back all compressed bytes from newly pinned exact commit, compare to original synthetic bytes; validate pre/post remote-ref stability and cumulative settlement parity. Preserve original `main` SHA unchanged.
- [ ] Independent reviewer signs run IDs, timestamps, archive SHA, main SHA and denied-control evidence. A passing local Git test is insufficient.

### Stage D — all producer and consumer migrations (REQUIRES APPROVAL)

- [ ] **P0-A:** Migrate `football-king-iphone.yml` (`archive_provenance`, `archive`) and `four-model-shadow-daily.yml` (`archive_ndr_capture`, `archive_openliga_capture`), never to an implicit or unprotected `main`.
- [ ] **P0-B:** Migrate all 12 source/market mutable latest and immutable-history writer workflows. Use explicit target refs and contract tests for each legacy read path, including `sources/latest.json`, BSD, weather, market/latest, quality gates and private redacted summary. Enforce freshness and forward-only history.
- [ ] **P0-C:** Replace `football-king-weekly.yml` unreviewed main Contents PUT with approved reporting artifact/PR route; verify old URLs.
- [ ] **iPhone:** Make official-readiness and daily-scorecard read the same vetted cumulative settlement object (not old `main:evidence/settled.json` for one and run-local evidence for the other). Compare exact results for original 105+ historical observations; preserve source and byte count. No silent fallbacks.
- [ ] Include negative tests for late-write collision, invalid/missing archive ref, source mismatch, truncated files, changed historical result, expired price, and bad permissions. Strict fail-closed HOLD throughout.

### Stage E — governance release review (LATER ONLY)

- [ ] With zero direct-main writers remaining (or explicitly paused/disabled with durable data retention), independently approve the main no-bypass Ruleset: require PR, at least one nonauthor approval, dismiss stale approval, block force-push/deletes, constrain actor bypass list to none as policy, verify effective admin enforcement.
- [ ] Required CI names must be **unique** and bound to their GitHub Actions source. Current generic `regression` names are not a safe unique status-check specification; disambiguate before configuring rules.
- [ ] Recheck effective branch/ruleset scope and negative write behavior on the exact commit in a safe fixture, never assume policy from a prose label.
- [ ] Re-run exact-head CI and capture independent sign-off only after all migration and read-parity tests.
- [ ] Keep model/recommendation activation separate; licenced tradable markets, verified FT/lineups/xG, external witness and genuine OOS EV require their own evidence.

## 4. Controlled rollback — data preserving, no force push

Stop/prohibit new production publishing when any cutover or read parity fails; status is `HOLD / DISABLED`. Preserve immutable archive contents and prior `main` data unmodified. Do **not** delete the archive branch, rewrite historical evidence, force-push a recovery commit, unprotect `main`, or reenable an old direct-main bot to recover service. An independent operator must review the failure, restore a previously verified **read-only historical view** or issue an approved remediation PR, maintain an append-only inventory of pending batches, and resume only after source/parity/permission checks pass. A deliberate temporary publication pause with visible HOLD is preferable to silent data loss or false green dashboards.

## 5. Exact acceptance receipt format for owner/reviewer

Record these separately with source URLs or saved checks (a JSON flag alone is not evidence):

- **Identity:** repository, default-branch exact SHA, pilot PR SHA, reviewer username, non-author approval, approver time, GitHub Ruleset IDs/effective rules and bypass actors.
- **Capability:** archive writer identity; repository + ref access, denied ability to mutate `main`, expiry/rotation evidence, no exposed PAT.
- **Canary:** authenticated remote archive ref and before/after SHA, job/run IDs, synthetic proof digests, replay results, collision result, independent read-back checks, unchanged main SHA.
- **Consumer continuity:** full legacy sample count/digest, new bounded sample count, mobile official/daily parity, other source/market freshness and missing/changed record negative tests.
- **Release gate:** explicit `main_ruleset_activation_authorized=false` until all owner-reviewed prerequisites complete; `production_recommendations=DISABLED` irrespective of CI outcome.

## 6. Today's verification status

| Gate | Status |
|---|---|
| 15 writer target mapping, pinned static source evidence | RESEARCH COMPLETE |
| Synthetic local bare Git write/replay/read tests | TESTED OFFLINE; no production proof |
| Official writer origin preflight present in research pilot | TESTED LOCALLY; no live credential proof |
| Current repo Rulesets returned | NONE |
| Main protection detail from connected GitHub read | 403 / UNVERIFIED |
| Real remote archive ref/protection/canary | NOT VERIFIED |
| All P0-A/P0-B/P0-C migration and site parity | NOT DEPLOYED |
| Independent reviewer | 0 |
| Main no-bypass Ruleset / real betting recommendations | **NOT AUTHORIZED / DISABLED** |

**Owner's next concrete dependency:** identify an independent reviewer and document authorized archive storage/ref/credential plan. No remote branch should be created until those conditions exist and are verifiable. Issues #569, #439 and #452 remain open.
