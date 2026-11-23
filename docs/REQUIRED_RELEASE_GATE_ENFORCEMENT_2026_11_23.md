# Football King — mandatory release check handoff (2026-11-23 HKT)

## Problem reproduced from existing repository configuration
`.github/workflows/football-king-regression.yml` currently restricts `pull_request` triggers to `ops/**` and selected workflow paths. A docs-only PR (e.g., #551) may receive only three lightweight checks and **does not necessarily run the complete ops regression**. Existing security blocker [#439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439) also warns that a generic job named `regression` exists in more than one workflow, making status-context selection ambiguous.

## Proposed candidate required check
Added `.github/workflows/football-king-required-release-gate.yml`:

- `on: pull_request` **without branch or path filters**; also `push` to `main` and manual dispatch, so document-only and workflow-only changes are examined.
- A single uniquely named job and check context **`football-king-required-release-gate`**; no collision with other `regression` jobs.
- Checkout and setup-python actions pinned to known full commit SHAs as already used in the repository.
- `permissions: contents: read`; checkout has `persist-credentials: false`; no PAT, bookmaker credential, licensed API key, source upload, secret injection, or privileged `pull_request_target`.
- Compile `ops` and run `python -m unittest discover -s ops/tests -q` across the complete synthetic/fail-closed suite on **every PR**.
- The job can run on stacked Draft PR branches, which are still not authorized for merge.

## Limitations
- A green result means Python syntax + regression tests passed for that exact commit; **not** that code is secure, a vendor license exists, a caller-supplied grant was independently signed, or bets have positive EV.
- GitHub branch protection is a **separate administrative setting** and is **not modified** by this PR. The workflow does not automatically become required just because the job is named that way.
- Path-unfiltered CI can increase usage on documentation-only PRs. This is intentional, to eliminate missing required status on those PRs.
- The check does **not** replace signed source data, trusted TSA, genuine two-source event verification, OOS research, or human reviewer signoff.
- If workflow actions are changed in future, update their immutable full SHAs; do not use mutable tags in this job.

## Owner/security-admin action required after independent reviewer approval
1. Confirm exact-head CI result and stable GitHub check name on this Draft PR; review the pull-request workflow for security and resource usage.
2. Independently verify current `main` branch rulesets and bypass access; current rules are **not verified by this candidate workflow**. Original security blocker #439 is still open.
3. In Settings → Rules → Rulesets (or branch protection), protect `main`, require PRs and an independent approving review after the latest push, no force-push/deletions, conversation resolution and admin/no-bypass enforcement.
4. Add the exact **`football-king-required-release-gate`** check status from GitHub Actions as a required check, using the GitHub Actions app as the trusted source, after confirming the exact context string. Keep existing essential jobs too after disambiguating their names.
5. Confirm a malicious PR or a docs-only PR cannot produce a skipped required status or bypass through another workflow. Check both direct and merge-queue behavior if merge queue is used; a future `merge_group` trigger would be required if the repository uses merge queue.
6. Do not merge the stacked research chain before its prior Draft PRs have been independently reviewed in dependency order.

## Safety baseline
`PRODUCTION_RECOMMENDATIONS=DISABLED`; no new source access, market data, odds verification, EV result, or changed model scoring. The code is a **candidate** enforcement mechanism until a human administrator configures and independently verifies branch protection.
