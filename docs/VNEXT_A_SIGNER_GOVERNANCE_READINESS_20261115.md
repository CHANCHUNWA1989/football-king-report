# PR #458 — Read-only protected-main signer governance readiness (administrative blocker)

Date: 2026-11-15 (HKT). **Research-only, unmerged, no signer activation, no provider fetch, no betting, HOLD/DISABLED.**

## Why this check is separate from Sigstore and model scoring

The existing `ops/original_a_dual_attestation_preflight.py` can interpret only freshly independently verified **future** source and A-link subjects emitted under a specifically pinned authorized `main` workflow. It deliberately does not create an attestation, nor can mocked policy-positive GH CLI output prove cryptographic authenticity. Before a signer can even be approved for a synthetic-only main canary, actual repository governance must be independently verifiable.

Draft [PR #438](https://github.com/CHANCHUNWA1989/football-king-report/pull/438) already specified protected-main requirements in `ops/vnext_pr09_signer_preflight.py`. This PR does **not** merge PR #438 or weaken its policy; the new diagnostic implements the matching requirements against the original A two-subject workflow's fixed expected file name. Real administrative changes are tracked in [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439).

## Newly committed read-only proof inventory

`ops/original_a_signer_governance_readiness.py` reads only these fixed GitHub REST resources via **GET** (no caller-selected host, no mutation):

- `/repos/CHANCHUNWA1989/football-king-report/branches/main`
- `/repos/CHANCHUNWA1989/football-king-report/branches/main/protection`
- `/repos/CHANCHUNWA1989/football-king-report/rulesets`
- `/repos/CHANCHUNWA1989/football-king-report/contents/.github/workflows/football-king-a-same-get-provenance.yml?ref=main`
- `/repos/CHANCHUNWA1989/football-king-report/pulls/458` and `/pulls/458/reviews?per_page=100`

It requires:
- exact `main` identity and protected flag, readable **actual branch protection details**, at least one independent approval policy, stale-review dismissal, after-last-push approval, protections enforced for administrators, strictly required CI, and branch force-push/deletion denied;
- the four explicit required GitHub Actions contexts matching PR #438 — `safety (3.11)`, `safety (3.12)`, `validate`, and `ledger-tests` — bound to **GitHub Actions app ID 15368**, never a generic all-green or ambiguous `regression` context;
- no unreviewed Ruleset bypass scopes (the stricter older branch-protection interface is not silently replaced with unexamined rulesets);
- an actual exact-path signer file present in `main`, **not** a Draft PR or unreviewed branch;
- non-Draft, open, unmerged PR #458, and a latest-state `APPROVED` review from a *distinct GitHub human account* on the PR's **exact current head SHA** (a bot, author self-review, stale SHA or later changed review status cannot substitute);
- if a signer run is considered, original GitHub-hosted `workflow_dispatch` context on `refs/heads/main`, exact repository numeric ID, expected current main SHA, and no PR/feature event pretending to be main.

The diagnostic always outputs `status=HOLD`, `production_recommendations=DISABLED`, `approved_main_signer_enabled=false`, `certified_prospective_samples=0`, `positive_ev_verified=false`, and no result/market/licence claims. A synthetic *policy-compliant fixture* sets only `governance_preflight_requirements_observed=true` while signing remains **disabled**.

It only emits safe blocker codes, never tokens, GH stderr, raw upstream match bytes or username-level approval lists. 403 on detailed protection is **a blocker**, not inferred compliance. 404 for expected workflow is **absent**, not a reason to create the workflow in the PR without admin and human approval.

### Actual repository observation, 2026-11-15

Read-only GitHub connector observations at this time:

- `main protected=false`; main commit `2f8be4c02b39cd55ed8e5f7323724426adcde6f4`
- repository Rulesets API returned `[]`
- `/branches/main/protection` returned **403**, meaning the available integration cannot independently audit admin/review/check/no-bypass controls
- `.github/workflows/football-king-a-same-get-provenance.yml` on main returned **404**
- PR #458 remained **Draft/open/unmerged**, with zero independent submitted reviews; head SHA is moving as new research commits are added

**Explicit actual current outcome:** `MAIN_NOT_PROTECTED`, `PROTECTION_READ_UNAVAILABLE`, `APPROVED_MAIN_SIGNER_WORKFLOW_ABSENT`, `RESEARCH_PR_NOT_READY_FOR_APPROVAL`, `CURRENT_HEAD_INDEPENDENT_HUMAN_APPROVAL_MISSING`. Missing authenticated signer means no real-source/A double Rekor proof or certified forward model samples. Actual main can change later; this historical snapshot does not certify future controls.

## Tests and live diagnostic

`ops/tests/test_original_a_signer_governance_readiness.py` runs synthetic adversarial cases for each policy rule and verifies fixed-host **GET-only** behavior, explicit GitHub admin read 403 denial, source-head drift, self/bot/stale approvals, wrong GitHub Actions app, unreviewed rulesets, missing signer main file and wrong dispatch context. **Mocked governance-compliant tests are not actual signed proof.**

Research workflow `.github/workflows/penaltyblog-two-model-pipeline.yml` runs those tests plus a **live GitHub read-only diagnostic** with workflow token scoped to `contents: read`. The live diagnostic is expected to emit HOLD blockers, but its step succeeds if HOLD is safely preserved; this does **not** mean the approval gate has passed. Its CLI contains no signing/exporting, GitHub writes, credential copying, publication, cron, or `attestations: write`.

Command for a local read-only check (not a signer):
```sh
python -m ops.original_a_signer_governance_readiness --live-readonly --require-hold
```

This command is safe to run without a token for public metadata, but private branch-protection details may be inaccessible; in that case it **must** return HOLD. An authorized admin can supply their own approved read-only inspection environment; do not paste an administrator PAT into issues, PR comments, logs or repository secrets.

## Admin acceptance, not an AI self-approval

The repository owner/security admin must configure and independently verify protection on `main` with required reviewers/CI/no-bypass. A genuinely independent human reviews current PR #438, #458 and their dependencies, with the latest commit and verified required workflows. Only after approvals and lawful source use can a separate narrowly-scoped **synthetic-only manual** two-stage signing workflow be proposed, reviewed, and introduced to protected main. Then a genuinely authenticated GitHub Sigstore/Rekor witness can be verified by the separate auditor before considering any real authorized live source capture.

**No real provider rights, authentic OOS improvement, executable odds, quote provenance, EV or betting readiness has been shown. Keep everything HOLD / DISABLED and do not force-merge.**
