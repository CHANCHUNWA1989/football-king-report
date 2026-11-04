# Football King VNext PR-09 — protected-main governance gate (research only)

Date: 2026-11-04. Status: **DRAFT / HOLD / NOT DEPLOYED**.

## Evidence snapshot and blocker (2026-11-04)

- GitHub repository CHANCHUNWA1989/football-king-report reports **main.protected=false**, commit 3d63b6f03aa2ce168674b22f71e7073bfbddc73b via the branch metadata API.
- GitHub repository rulesets API returned an **empty list**; no configured ruleset can be inferred from that output.
- The branch-protection detail endpoint returned **403 Resource not accessible by integration**. The connector could not independently inspect the required-review and status-check policy. Treat this **as UNKNOWN / BLOCK**, not as proof policies exist or do not exist beyond the explicit protected=false branch metadata.
- PR #429, #430, #431, #433, #434, #435, #436, #437 are all open **Draft**, none merged. PR #437 currently has **zero submitted reviews**. Distinct PR #432 is an alternative PR-03 against PR-02, **not on this stacked lineage**; do not merge both alternatives automatically.
- The earlier 5/5 CI workflows for PR #437 validate local code and contract tests, **not** a genuine main-branch GitHub OIDC/Sigstore signature or Rekor witness.

This engineering review does **not** constitute independent human security approval.

## PR-09 research scope

This PR stacks on PR #437; it does **not** activate the signer, approve or merge PRs, alter branch protection, gain provider rights, or enable live betting.

- New ops/vnext_pr09_signer_preflight.py pins GitHub repository and ID, main ref, manual dispatch, SHA, run identity. It reads only the canonical branch and branch-protection endpoints and fails on mismatched main commit, unprotected main, missing independent PR approval policy, stale approval allowance, absent last-push approval, admin bypass, missing strict CI, force pushes, or branch deletions.
- Updated synthetic signer workflow runs this preflight **before** attempting the local canary or Sigstore signing. API 403 or bad token fails closed.
- New ops/tests/test_vnext_pr09_signer_preflight.py tests negative security cases without provider secrets, real signals, or network access.

## Acceptance checklist

- [x] Observe main.protected=false and classify as a hard blocker.
- [x] Observe read-only integration receives 403 for detailed protection policy.
- [x] Implement fail-closed synthetic signer governance preflight and offline tests.
- [ ] Verify CI on **final exact HEAD**, inspect job logs.
- [ ] An administrator configures independent PR review, strict required checks, last-push review, no admin bypass, no force pushes, no deletion.
- [ ] GitHub API access permits independently reading protection settings without exposing private credentials. If inaccessible, stay disabled: never skip this gate.
- [ ] An independent reviewer approves upstream stack in order. Do not self-approve or bypass required review.
- [ ] Only then run the synthetic main-only manual signer and independently verify genuine GitHub/Sigstore/Rekor bytes.

## Continuing HOLD policy

The signer preflight is deliberately blocked under the repository's current settings. Passing test mocks is not a substitute for an independent real approval. A synthetic signature, even if genuine, does **not** prove actual fixture identity, provider licensing, source independence, matched prospective OOS superiority, executable odds, CLV, ROI or positive EV. **No model scoring or production betting recommendations. HOLD / DISABLED.**

## References

- https://github.com/CHANCHUNWA1989/football-king-report/pull/437
- https://api.github.com/repos/CHANCHUNWA1989/football-king-report/branches/main
- https://api.github.com/repos/CHANCHUNWA1989/football-king-report/rulesets

## Security audit follow-up: required CI spoofing prevented

On the PR-09 security follow-up, review of the preflight found that checking only a **non-empty required status-check list** would accept an irrelevant green check as if it were security CI. This was tightened to require **all** of the following canonical GitHub Actions check contexts with **GitHub Actions app ID 15368** (verified on PR-09 head check-runs API): `safety (3.11)`, `safety (3.12)`, `validate`, `ledger-tests`. A missing check, any-source/unbound context-only configuration, malformed app ID or wrong app is refused. These checks are stable relative to the observed CI head, but may require re-review if workflows are renamed.

The check named `regression` is currently published by two distinct workflows; GitHub explicitly warns duplicate job names can block merging when selected as a required status check. Rename to unique job context before requiring it, rather than treating duplicate-name approval as reliable evidence.

The current branch protection 403 / absent protection status remains the main hard blocker. The CI update only proves simulated failure-path handling, **not** that real protected-main settings have been configured. Track repository-owner actions at [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439).
