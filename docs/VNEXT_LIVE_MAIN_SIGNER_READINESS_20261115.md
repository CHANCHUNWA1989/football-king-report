# VNext — LIVE GitHub governance/signing-readiness observation

Date: 2026-11-15 HKT. This is a **real GitHub API read-only inventory** added to Draft PR #458. It is NOT a new signer, branch-protection configuration, an attestation verification, source licence approval or a production release.

## Why a live check rather than another mocked signer

The existing [Draft PR #438](https://github.com/CHANCHUNWA1989/football-king-report/pull/438) contains `ops/vnext_pr09_signer_preflight.py`, the formal fail-closed **protected-main governance requirement**: matching current main SHA, at least one independently required PR reviewer with dismiss-stale and last-push approval, admin enforcement, strict current required CI bound to the GitHub Actions app, no force-push or delete, detailed branch-protection API readable by an authorized reviewer, workflow dispatch and exact main context. It remains separate, unmerged and must not be bypassed or replaced with a lower standard.

Our separate original A/source double-Rekor verifier in PR #458 is also still research-only. Its documented future signer workflow `.github/workflows/football-king-a-same-get-provenance.yml` **is absent from main**; no trusted real signatures are currently claimed. A green mocked `gh attestation verify` policy test does not mean signers or reviewer approval have been provisioned.

## What changed

- `ops/vnext_live_main_signer_blocker_inventory.py`: uses **only 6 fixed, repository-scoped GETs against the actual GitHub API** and a read-only `GITHUB_TOKEN` in research CI: `branches/main`, `branches/main/protection`, `rulesets`, the exact **main** signer workflow content path, PR #458 metadata, and PR #458 reviews. Does NOT call any write endpoint, `gh attestation`, signer, external bookmaker or source fetch. No token is printed.
- Its report is always `status=HOLD`, `production_recommendations=DISABLED`, `signer_authorized=false`, `attested_original_a_and_source=false`, `certified_prospective_samples=0`, `positive_ev_verified=false`. A 403 on detailed branch protection is explicitly a blocker. A 404 for the signer file means **missing on main**, not "maybe available" or "ready".
- It records PR current head SHA and only *observes* distinct current-HEAD approvals excluding the PR author and automated bots; it never claims that a current-HEAD review observation replaces the protection rule enforcement, the dependency PR chain, or independent source rights. 100 review objects without pagination is ambiguous and remains blocked. A draft, stale approval, self-review, or foreign signer can never be promoted through this tool.
- `ops/tests/test_vnext_live_main_signer_blocker_inventory.py`: adversarial **offline mocked API** tests. The actual GitHub API is queried **separately** in `.github/workflows/penaltyblog-two-model-pipeline.yml` new `live-readonly-signer-inventory` job, which has **only** `contents: read` and `pull-requests: read` permissions, no write permission, no secrets and no publishing. The job requires the real branch and PR metadata to have been read, then asserts all model/EV/signing claims remain disabled. It prints only sanitized blocker codes and simple counts.

If GitHub protection configuration is inaccessible because the integration cannot read it, the job can still complete an observational HOLD report, but **cannot approve signing**. A new protected-main admin audit and signer installation remain separate authorized human operations. Never treat a CI status "success" here as an acceptance of the governance controls.

## Direct live evidence checked 2026-11-15 HKT

- `GET /repos/CHANCHUNWA1989/football-king-report/branches/main` reported `protected=false`; observed SHA `2f8be4c02b39cd55ed8e5f7323724426adcde6f4` at the initial check.
- `GET /repos/CHANCHUNWA1989/football-king-report/rulesets` returned `[]`.
- `GET /repos/CHANCHUNWA1989/football-king-report/contents/.github/workflows/football-king-a-same-get-provenance.yml?ref=main` returned 404.
- PR #458 was OPEN / DRAFT / UNMERGED at HEAD `fe9e702f7bb3cdff84274357557ca23ef1f38d02` before these subsequent research-only commits. Current HEAD is automatically queried by the new CI job, not frozen to this old one.

These data are live observations from that moment; they must be rechecked before any future decision. Neither an empty ruleset list nor a branch metadata boolean on its own establishes the entire approval policy.

## Next hard blockers / ownership

1. Authorized repository owner/security admin configures protected `main` with independent last-push human approval, strict unique app-bound required checks, enforcement for administrators, no force-push/deletion, and accessible independent read-only proof. See [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439).
2. Independent security reviewer examines PR #438 governance gate and approves a **future** main-only signer design. The formal signing workflow for this precise A-source/link format must be reviewed separately and may only be deployed after protection and external legal-source permissions. This PR **does not** install it or mint any signature.
3. A legitimately authorized prospective OpenLigaDB source must be captured **before** original A and both A/Poisson/DC model cutoffs, using the *same actual raw GET*. Do not rerun a later collector or retroactively date old files. The two independent Rekor subjects are not proof of publisher truth, independent actual kickoff, results, bookmaker quotes or model uplift.
4. Continue `HOLD / DISABLED`; zero certified prospective samples and zero verified positive EV until independent real-world evidence exists.
