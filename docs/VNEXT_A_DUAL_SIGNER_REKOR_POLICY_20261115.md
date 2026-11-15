# PR #458 — Main-only, two-subject original A/GET Sigstore-Rekor preflight

**Research design date:** 2026-11-15 (UTC) / 2026-11-15 (HKT).
**All paths remain Draft / HOLD / DISABLED. No live trusted attestation was created or validated by this PR.**

## Fixed purpose

The existing `ops/original_a_same_get_private_seal.py` preserves the raw OpenLigaDB HTTP body already read by original A's one GET (private, opt-in, no second source request). The existing `ops/original_a_same_get_shadow_pair.py` separately creates a private, SHA256-named `shadow.json + link.json` tar. The local `link.json` retains exact original A source SHA, original A 1X2 vectors, observed typed match/team IDs, original A claimed decision time and kickoff.

**Neither local SHA256 nor the claimed UTC timestamp is an external witness.** The 2026-11-15 actual older GitHub cross-run audit already established a separate OpenLigaDB collector ran *after* a 29-prediction A snapshot; those historical samples cannot be healed by this new code or newly issued signatures.

## Two separate, independent signed subjects (future-approved main only)

`ops/original_a_dual_attestation_preflight.py` is a **read-only, opt-in verifier**, not a signer or publisher. It accepts two already-preserved source files and **two independently obtained Sigstore bundles**, all in owner-private working directories, and re-verifies each subject by invoking the GitHub CLI at run time:

- Source: exact original `<sha256>.openliga-private.tar`, accompanied by `source.sigstore.json`.
- A link: exact original `<sha256>.a-source-link-private.tar`, accompanied by `link.sigstore.json`.
- Separate source signer run ID/attempt and separate A-link signer run ID/attempt. A single run/attempt cannot substitute for two independently witnessed moments.
- A **future** authorized, independently reviewed and protected `main` workflow path is pinned by policy to `.github/workflows/football-king-a-same-get-provenance.yml`. This workflow is **not currently installed or approved on main**; simply passing its name to a verifier is NOT proof a signer exists. The code rejects signatures from pull-request, research or arbitrary GitHub workflow identities.
- Pin exact repository name and numeric owner/repository IDs, expected source-commit SHA, signer-workflow SHA, GitHub-hosted runner, issuer, `refs/heads/main` and both run IDs. `gh attestation verify` uses the original supplied subject and bundle bytes, `--repo`, `--signer-workflow`, `--source-ref refs/heads/main`, `--source-digest`, `--signer-digest`, `--deny-self-hosted-runners`, then freshly checks the CLI's single verification result, exact certificate, one Rekor Tlog at `https://rekor.sigstore.dev`, exact signed subject filename and SHA256, and same bytes on re-read.
- **Chronology:** original source's already-existing claimed reception time <= separately Rekor-witnessed source-subject time <= original A's claimed generation completion; original A completion <= independently Rekor-witnessed A-link-subject time <= the **earliest recorded** kickoff - 10 minutes.
- This timing does **NOT** independently authenticate the model's self-claimed forecast-completion time, publisher identity, legal data rights, actual kickoff or historical-result truth. It only establishes subject-byte existence on an independently witnessed timeline **if fresh verification succeeds**.
- Each verification result remains `status=HOLD`, `production_recommendations=DISABLED`, `source_publisher_authenticated=false`, `actual_kickoff_independently_authenticated=false`, `training_data_rights_verified=false`, `certified_prospective_samples=0`, `positive_ev_verified=false`. There is no code path to betting enablement.

### Offline invocation illustration (NOT yet executable against approved real-main subjects)

```sh
python -m ops.original_a_dual_attestation_preflight \
  --original-dir /private/a/source \
  --pair-file /private/a/links/EXACT_PAIR_SHA256.a-source-link-private.tar \
  --proof-dir /private/a/sigstore-bundles \
  --original-sha EXACT_SOURCE_SHA256 \
  --pair-sha EXACT_PAIR_SHA256 \
  --source-sha EXACT_APPROVED_MAIN_COMMIT_SHA \
  --workflow-sha EXACT_APPROVED_MAIN_WORKFLOW_COMMIT_SHA \
  --source-run EXACT_EARLIER_MAIN_RUN_ID \
  --source-attempt 1 \
  --link-run EXACT_LATER_MAIN_RUN_ID \
  --link-attempt 1
```

All placeholders are explanatory and **not actual signed proof data**. Signature bundles must be obtained by a legitimately approved, protected-main workflow; **do not mint self-signed proof objects from the research PR**. This PR does not add, trigger or deploy a workflow with `attestations: write`, nor any cron. It does not publish private OpenLigaDB bytes or prediction results. Legal sharing/attribution requirements must be assessed separately before any externally accessible storage.

## Adversarial CI

`ops/tests/test_original_a_dual_attestation_preflight.py` uses a private **synthetic** original A/source pair and **mocked** `gh attestation verify` stdout, NOT actual cryptographic signatures. Tests assert pinned workflow identity, two CLI invocations, exact subject and bundle digests, strict chronology and failure under missing CLI, missing/unsafe files, wrong subjects, non-main source, false signer, missing Rekor, mismatched recorded kickoff and unauthorized proof fields. A test returning `audit_completed=true` when the GH CLI is MOCKED proves only the validation policy code, not the real presence of authorized witness or signing ability.

`.github/workflows/penaltyblog-two-model-pipeline.yml` invokes these tests only as research CI; it never invokes an attestation signature creation, nor does it claim a verified actual-signer result.

## Remaining independent gates

1. Repository admin must enable protected-main rules and independent reviews (tracked by [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439)).
2. Authorized data stewardship must approve legal storage/use of upstream raw match bytes; only then introduce, review and approve an actual protected-main, two-step sign/witness procedure with access control. A source witness must occur before generating A and a link witness after, not a retrospectively minted signature on 2026-11-15 historical inputs.
3. Then run this verifier **with genuine fresh GitHub CLI** (not mocked or a saved verification JSON), check real source clock/actual kickoff and fixtures externally, and separately register a genuine next-match A+Poisson/DC same-cutoff prospective cohort. No gain/positive EV claim without independent future evidence and executable verified market quotes.

**Current state: signer workflow not deployed; zero actual authenticated double-subject evidence; PR #458 Draft/unmerged; HOLD/DISABLED.**
