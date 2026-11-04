# Football King VNext PR-10 — unique required CI check identities (research only)

**2026-11-04 · Draft / HOLD / DISABLED.** Stacked on PR #438 → #437 → #436 → #435 → #434 → #433 → #431 → #430 → #429. The alternative #432 is deliberately excluded from this lineage.

## Verified blocker at start of this PR

- On PR-09 exact head, two different workflow jobs reported the same check name `regression`:
  - `.github/workflows/football-king-ci.yml` → `jobs.regression` (full safety regression)
  - `.github/workflows/football-king-regression.yml` → `jobs.regression` (failover regression)
- The check-runs endpoint identified both as GitHub Actions app ID **15368**. Having the same check name in separate workflows creates ambiguity for required branch status checks, potentially blocking merges or weakening the intended control.
- Repository `main.protected=false` remains observed. Read access to `branches/main/protection` remains **403** via this connection, so actual review protection cannot be validated or configured.
- No main-only GitHub OIDC / Sigstore / Rekor signer execution exists for PR-08, and no independent real-data licensing, source independence, OOS benefit or EV has been proved.

## Change set

1. Rename only the two colliding job IDs, preserving their commands and permissions:
   - `football-king-ci.yml`: `regression` → `security-regression`
   - `football-king-regression.yml`: `regression` → `failover-regression`
2. Tighten `ops/vnext_pr09_signer_preflight.py`: require both uniquely named job contexts **in addition to** `safety (3.11)`, `safety (3.12)`, `validate`, `ledger-tests`. All six must be bound to GitHub Actions app ID **15368**, with strict branch status checks, independent PR review, last-push approval, no admin bypass, no force-push/delete and an exact GitHub main commit.
3. Update `ops/tests/test_vnext_pr09_signer_preflight.py` and introduce `ops/tests/test_vnext_pr10_unique_required_checks.py`: reject missing or spoofed regression suites, malformed checks, duplicate legacy names as substitute, wrong workflow identity and incompatible protected-branch rules.

## Non-deployment and migration

- All changes are **research branch only**. No PR has been merged, no branch security setting altered, no signer dispatched and no market feed or bet touched.
- When GitHub branch protection is properly configured by an authorized repository administrator, select the **new** `security-regression` and `failover-regression` contexts from this same HEAD **after the workflows have actually run**, and retain the other four app-pinned checks. Do not configure nonexistent check names prematurely on `main` (would deadlock required checks).
- This refactor deliberately does not redefine the underlying test suites; their independence is workflow/job-name uniqueness, not statistical model independence or provider-source independence.
- Any inability to inspect governance (403), absent reviewer, unprotected branch, missing exact required contexts or wrong SHA is fail-closed **HOLD**, not an invitation to bypass an API.
- PR-08 future signer workflow remains manual/main-only; actual Sigstore and Rekor verification still requires separately observed real evidence. Passing mock tests does not certify any signature or forecast.

## CI acceptance

- `python -m compileall -q ops`
- `python -m unittest discover -s ops/tests -q`
- Two new names visible as distinct **GitHub Actions check runs on exact PR-10 head** with successful status.
- Original V4.1 compatibility, repository safety, offline 1X2 and ledger CI remain green.
- Independent human security review plus upstream PR approval/merge order remain mandatory before considering production main changes.

Track administration / review blocking prerequisites at [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439).

**Always `production_recommendations=DISABLED`, `model_scoring_eligible=False`, `positive_ev_verified=False`.**
