# Fourth-stage forward evidence admission: duplicate identity quarantine

Date: 2026-11-21 HKT. **Draft research change; production remains DISABLED.**

## Code-audited finding

On main, `ops/forward_settlement_audit.py::audit` checked duplicate identities against a `seen` set that was updated only after a record passed the candidate checks. When two rows claimed the same `(event_id, model_version, market)`, the function could accept the first row and reject the second, or accept the only otherwise-valid row while a conflicting or invalid duplicate existed. The selected row thus depended on caller input order and potentially post-match rewriting. This is not acceptable for prospective evidence integrity, even in a research-only evaluation.

## Fix

- Pre-scan all correctly shaped identity triples among input rows, without reading probabilities or outcomes to choose a preferred row.
- If any identity occurs more than once, exclude **every** record for that identity (even when one is otherwise invalid, or was created after kickoff). Do not trust the first, last, highest-scoring or winning row.
- Report `duplicate_identity_groups_rejected` and `duplicate_rows_rejected` for auditability.
- Preserve the unchanged output fields that already make this *self-attested candidate research*: `independent_forward_samples=0`, `authenticated_forward_samples=0`, `statistical_significance_verified=false`, `positive_ev_proven=false`, `model_promotion_allowed=false`, `production_recommendations=DISABLED`.

The fix does **not** establish genuine immutable prediction creation, Sigstore/Rekor or TSA, provider-source independence, fixture identity equivalence across providers, executable odds or model edge. Positive submitted evidence flags remain untrusted claims.

## Regression and release gates

- Duplicate exact row: both are excluded (zero candidates), not one accepted.
- Conflicting probability/outcome versions: all are excluded in all three input orders.
- One invalid source-authentication flag or one post-kickoff prediction: cannot be hidden by a valid duplicate.
- Distinct model versions or markets retain their existing research-candidate meaning, not formal certified settlements.
- Check full repository CI, peer review, branch-base consistency and source-native provenance before merging. No production or betting authorization.

## Continuing fourth-stage workflow

The **next evidence prerequisite** is not another retrospective winner: capture a real pre-kickoff source-native forecast payload and contemporaneous market quote, hash the exact bytes and use a genuinely independent attestation of capture time. Only later link to two source-native finished-score reports with exact fixture identities and conflict handling. If any link is missing, preserve HOLD; do not increase certified sample counts. Maintain paired, chronology-safe out-of-sample comparisons for A vs challenger vs market only after evidence is independently verified.
