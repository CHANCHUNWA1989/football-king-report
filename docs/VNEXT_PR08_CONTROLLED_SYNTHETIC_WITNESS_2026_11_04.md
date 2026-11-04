# Football King VNext PR-08 — Controlled synthetic witness canary

Date: 2026-11-04. Status: **RESEARCH / DRAFT / HOLD**.

## Dependency chain and scope

PR-08 stacks on the unmerged PR-07 research branch, which itself depends on PR-06 → PR-05 → PR-04 → PR-03 → PR-02 → PR-01. None of these changes is a production deployment. Keep `main`, A/B/C forecasts, existing scraping schedules, real provider credentials, bookmaker interfaces and wagering unchanged.

## Research deliverables

- `.github/workflows/football-king-vnext-forecast-attest.yml` defines a **manual-dispatch-only**, repository-and-main-restricted GitHub-hosted runner job with narrowly scoped attestation permissions and SHA-pinned actions.
- `ops/vnext_pr08_canary.py` generates exactly one locally sealed, **synthetic** baseline/challenger 1X2 forecast pair with explicit simulated fixture and source IDs, no real data and no results. The local seal is always `external_clock_attested=False`; no synthetic record is admitted into model scoring.
- `ops/tests/test_vnext_pr08_canary.py` checks the synthetic marker, archive hash and permissions, time ordering, invalid identity/clock, overwrite/symlink refusal, tampering and the restricted workflow contract.
- The signer job is intended to produce a GitHub OIDC/Sigstore attestation for exact synthetic seal bytes, then independently execute the existing PR-07 verifier against the bundle and require `WITNESSED_BYTES_RESEARCH` plus `production_recommendations=DISABLED`.

## Fail-closed rules

1. A PR, fork, push, schedule or a branch other than `main` must not invoke the signer job. Until independently reviewed and merged as part of the ordered dependency chain, **there is no deployed signer on main**.
2. No claim of real signature verification may be made from mocked tests, a draft workflow, unit-test output or CI success. Record exact workflow run, signer identity, subject SHA256 and Rekor witness evidence only after a real trusted run and independent cryptographic re-verification.
3. Even genuine GitHub attestation would only bind bytes and witness time. It would **not** establish real fixture identity, authorized provider rights, upstream source independence, official results, untouched out-of-sample improvement or executable bookmaker quotes.
4. The synthetic canary is strictly excluded from PR-06 cohort eligibility and all EV/ROI calculations. All actual data-source onboarding and forecast-result promotion remain `HOLD`; `model_scoring_eligible=False`, `positive_ev_verified=False`, `production_recommendations=DISABLED`.
5. Any mismatch, unavailable signer, missing bundle, invalid timestamp, changed subject bytes, insufficient rights, unverified result provenance or failed test must fail closed; do not reroute into live operations.

## Acceptance checklist

- [x] PR-07 dependency audited and research branch created.
- [x] SHA-pinned restricted workflow committed.
- [x] Synthetic canary producer committed.
- [x] Offline adversarial tests committed.
- [ ] GitHub PR CI successful for the **exact final head commit**, raw test log inspected.
- [ ] Independent security and data-rights review.
- [ ] Ordered upstream merges approved by reviewers.
- [ ] Real main-only manual synthetic signer run and independently verified Sigstore/Rekor proof.
- [ ] Separately licensed real forward fixtures and independently authenticated results, if later authorized.

A draft PR with passing CI is **not** approval for merging or activating real-data or betting functions.
