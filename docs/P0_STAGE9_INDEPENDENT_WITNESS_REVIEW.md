# P0 custody witness independent review proposal — HOLD / DISABLED

This is a reviewable proposal, not authorization and not an active signing workflow.
The original 88-path subject stays immutable. The new linked subject binds its digest,
the exact 89-path subject, the new German gzip, and the changed source pointer.

## Independent approval gates

1. Reviewer not author verifies both candidate commits, both canonical subject hashes,
   exact CI results, full tree deltas and the preserved archive pointer bytes.
2. Repository owner provisions a dedicated protected GitHub environment with independent
   required reviewer and prevent-self-review. Confirm actual effective protections and
   no bypass before approval. Do not infer approval from a JSON flag.
3. Only after independent approval, implement a manually dispatched signer on the reviewed
   main commit. No pull_request_target; no arbitrary subject URLs or caller-selected files.
   Rebuild exact linked subject from pins, compare SHA-256, then sign only this subject.
   Grant only contents:read, id-token:write and attestations:write for signing job.
   No contents:write, no archive push, no market/model privileges.
4. Verify actual Sigstore bundle using a trusted verifier, pinned repository/workflow/commit,
   GitHub-hosted identity and verified Rekor inclusion/time. The prior verifier is intentionally
   pinned to the old 88-path subject and cannot approve the new linked subject.
   Extend and independently review the exact-subject verifier for the new schema/digest
   before signing; do not loosen the original verifier.
5. Independently select RFC3161 TSA policy OID, CA chain, revocation policy, and retention.
   Submit only the SHA256 request, not source data. Preserve the exact TSQ and TSR.
   Verify nonce, imprint, chain, timestamp and approved policy. Local fixture CA is not trust.
6. Retain independent proof and nonauthor review of the exact head, separate from GitHub
   archive. No evidence here demonstrates independent retention or authorization to write.
7. All release flags remain false and production recommendations DISABLED. Any failure
   leaves HOLD. No automatic signing or external submission in this proposal.

## Current blockers

No reviewed signer workflow on main, no independent reviewer, no approved TSA policy/CA,
no real witness for either subject, and no demonstrated protected archive writer identity.
The new linked subject is unsigned. Schedule monitor remains a draft; a single German
recovery does not prove hourly cadence.
