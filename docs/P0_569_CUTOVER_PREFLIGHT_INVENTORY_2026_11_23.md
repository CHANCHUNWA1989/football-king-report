# P0 #569 — research-only static archive cutover blocker inventory (2026-11-23 HKT)

**Draft / NOT a deployment decision. Always HOLD / DISABLED.**

## Scope and execution

Added \`ops/archive_cutover_preflight.py\` (Python standard library only) and \`ops/tests/test_archive_cutover_preflight.py\` in PR #571.

Read-only command:

\`\`\`bash
python -m ops.archive_cutover_preflight --workflow .github/workflows/football-king-iphone.yml
\`\`\`

The command outputs a bounded JSON diagnostic with a SHA-256 of the inspected workflow, names of jobs with *literal* \`git push origin HEAD:refs/heads/main\` commands (allowing a \`git -C\` checkout argument), literal \`gh api -X PUT\` operations on \`contents/evidence/settled.json\`, \`contents: write\` job markers, and limited downstream read-path markers. It **always exits nonzero**, even if known write strings disappear, and always sets \`ruleset_activation_authorized=false\` and \`production_recommendations=DISABLED\`.

## Verified unresolved blocker in the existing main workflow

The currently deployed \`.github/workflows/football-king-iphone.yml\` contains:
1. Job \`archive_provenance\` with direct \`HEAD:refs/heads/main\` push.
2. Job \`archive\` with another direct \`HEAD:refs/heads/main\` push and \`gh api -X PUT\` on \`evidence/settled.json\`.
3. Both archive jobs request \`contents: write\`.

The report must say \`HOLD_LEGACY_MAIN_WRITERS_PRESENT\` while these are present. The suite includes a test using the actual checked-in workflow, plus synthetic tests for missing jobs, comment-only mentions, missing/large files, and a mock migration in which write strings disappear (which must **still** remain HOLD).

## Critically limited signal

This is a **static pattern inventory**, *not* full AST/script analysis, GitHub policy inspection, authenticated branch probing, independent review, complete producer/consumer discovery, or authorization to enforce a no-bypass Ruleset. It may miss indirect writes, aliases, other workflows and reusable jobs. If the tool stops matching existing commands after refactoring, the correct conclusion is \`HOLD_MIGRATION_NOT_INDEPENDENTLY_VERIFIED\`, never READY.

The PR still has no proven real isolated remote canary, no independent human reviewer, no full read-path parity or migration of all legacy writers. The earlier five failed \`evidence/settled.json\` PUT retries lack real status evidence; do not guess concurrency or permission failures.

## Remaining acceptance steps (owner / independent reviewer)

- Independently inventory **all** repository default-branch writers, reusable workflows, API paths and downstream public/mobile readers; sign off on a branch-isolated source and retention/rollback plan.
- Provision and protect \`research/forward-provenance-archive\` only after approved permission design; run a separately authorized **synthetic-only** authenticated, non-force, no-main-write remote canary. Do not put licensed raw feeds or secrets into public archives.
- Demonstrate byte-identical historical read parity and all-settlement continuity, with preserved original 105-sample research legacy and explicit fail-closed handling.
- Obtain real independent code review and exact-head CI pass *after* all changes. Only then review governance issue #439 for a no-bypass \`main\` Ruleset; keep #452 provider licensing, source rights, OOS and positive EV separately blocked.

Do not auto-merge, self-approve, enable production betting or treat CI/pinned Git blobs as trusted football match outcomes. 
