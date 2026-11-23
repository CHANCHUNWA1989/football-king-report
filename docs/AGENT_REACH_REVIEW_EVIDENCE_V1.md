# Agent Reach Independent Review Evidence Gate V1 — advisory only

This change is deliberately restricted to PR #521 first; other stacked research PRs remain Draft. It is **not a replacement for GitHub's branch ruleset / protected branch**, and never approves or merges code.

## Why this exists

The repository has no observed submitted independent review for #521. CI was previously green, which proves the existing tests passed but says nothing about an independent human's acceptance. Repository rulesets listing is empty; the connector receives HTTP 403 when trying to read `main` branch protection, so protection **cannot be confirmed**. A green CI result must never silently be treated as an approval.

## Advisory review check

- `ops/agent_reach_review_guard.py` operates on a **GitHub PR metadata JSON snapshot** and the list of **submitted review records**. Its tests never use a real token or external API.
- A matching non-author, human `APPROVED` review must refer to the PR's **exact latest Git head commit SHA**, with a GitHub owner/member/collaborator association. Self approvals, bots, draft/PENDING reviews, review of old SHA, latest COMMENTED or DISMISSED vote, and outstanding CHANGES_REQUESTED vote fail closed.
- `.github/workflows/agent-reach-review-evidence.yml` requests **read-only** GitHub pull-request metadata using the built-in GITHUB_TOKEN. It fails closed on API error, pagination, malformed data, or missing independent approval. GitHub tokens and review bodies are never printed or committed.
- **Current reviewer permission evidence:** `author_association` (owner/member/collaborator) by itself is not proof of **current** repository write access. For at most ten human, non-author exact-head APPROVED reviewers, the read-only job now queries `GET /repos/{owner}/{repo}/collaborators/{login}/permission`, verifies the response login and one of `write`, `maintain`, `admin`. Missing data, mismatched login, `read` / `triage` / `none`, invalid data, API errors or HTTP 403 produce HOLD. Only if current permission is verified does the receipt set `reviewer_write_permission_verified=true`. This still **does not constitute a required GitHub branch rule or authority to merge**.
- An **expected failure due to zero approvals is a deliberate blocked gate, not a broken test**. The synthetic test job must pass before the integration review check decides `REVIEW_GATE_HOLD`.
- **TOCTOU guard:** The workflow fetches GitHub PR metadata before and after reading reviews, and compares the two GitHub API snapshots against the immutable triggering event's PR number/head SHA, author and base ref. Any mismatch, branch switch, new commit or changed draft/merged state yields `STALE_OR_MISMATCHED_PR_SNAPSHOT` and holds. This closes the observed mid-fetch race, **but cannot prevent a push after the final read**; protected-branch enforcement is still necessary.
- The structured output always remains `HOLD`, `production_recommendations=DISABLED`, `eligible_for_model=false`, `verified_positive_ev=null` even if a valid review is observed. Approval does **not** authorize live sports collection or bets.

## Limitations

**Not an enforceable protected-branch check.** GitHub will enforce a required status only after repository administrators configure an active ruleset / branch protection for `main`. This workflow lives in the research branch until merge; an author with PR code write access could alter its implementation. Also, GitHub `author_association` does not prove write permissions. This script explicitly marks `reviewer_write_permission_verified=false` and `github_branch_protection_verified=false`; reviewers and permissions require separate administrative verification.

For proper enforcement, a **trusted workflow on the default branch** and repository-level rules that disallow bypass, force-push and unreviewed merging are necessary. Existing #539 tracks the admin-dependent setup. The `pull_request_review` workflow trigger may be restricted before it exists on default; if a review arrives, manually recheck the exact PR head and Github checks rather than assuming a new workflow ran.

Nothing in this change modifies football models, sealed snapshots, odds APIs, HKJC sources, production release, or data quotas. The existing new URL canonicalization safety fix must remain unchanged. Do not merge without independent reviewer approval and all relevant non-advisory CI passing.

## Explicit acceptance

1. Offline unit tests show current-head human nonauthor approval can be **observed** while every stale, dismissed, bot, self-review and review-blocking case is rejected.
2. GitHub Action fetches actual current #521 metadata and fails with `REVIEW_GATE_HOLD` when there are zero submitted approvals.
3. #521 remains Open, not merged, and its formal betting flag remains `DISABLED`.
4. Admin ruleset and nonauthor reviewer remain outstanding; recording a red advisory check cannot masquerade as configuring an enforced GitHub rule.
