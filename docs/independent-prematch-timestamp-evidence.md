# Independent pre-match timestamp evidence: release gate

This is a **research-only** evidence procedure for draft PRs #461 and #462.
A local SHA-256 hash and `capture_utc` field do not establish that a forecast
existed before kickoff. A Git commit authored date or user-supplied
`independently_timestamped=true` field is likewise not sufficient.

## Required evidence for each forecast

1. **Original sealed receipt**: preserve raw bytes, SHA-256, source namespace,
   fixture ID, model ID/version, 1X2 probabilities and UTC cutoff.
2. **Independent external timestamp**: obtain a timestamp authority receipt
   (e.g. an RFC 3161 timestamp token), or a documented third-party immutable
   event whose recorded time is independently verifiable. Preserve the original
   binary token / external event identifier; do not substitute a screenshot,
   local clock, or self-authored timestamp.
3. **Verification**: validate the token's signature, trust chain, digest
   binding to the exact sealed bytes, UTC time and relevant trust policy with
   an independently maintained verifier. Document verifier version, trusted
   authority and certificate policy. Reject revoked, expired-at-signing or
   otherwise untrusted signing credentials as required by policy.
4. **Timing**: independent evidence must predate the fixture's verified
   kickoff; both original and challenger forecasts must have the same
   documented `as_of_utc` cutoff. Record actual acquisition time separately.
5. **Source provenance**: keep independent source records for fixture identity,
   kickoff, match result and any market quote; record timestamps, provider IDs,
   access rights and data corrections. Never infer authenticity from caller
   flags.
6. **Reviewer sign-off**: a person independent of the code author must review
   the evidence bundle and release gates, including Issue #439 branch protection.

## Current implementation boundary

`ops/paired_seal_intake.py` only checks local hash, probability validity,
fixture identity and claimed timing. It deliberately returns **HOLD** even
when local checks pass. It **does not** validate RFC 3161, public logs, GitHub
timestamps, external signatures or independent match results. Therefore
`independently_timestamped` must remain untrusted; no automation may
promote a pair to verified from a boolean field.

## Suggested next engineering milestone

Implement a separate, pinned-dependency RFC 3161 signature and trust-policy
verifier with offline fixtures and negative tests (forged token, altered
receipt, wrong authority, post-kickoff timestamp, revoked/expired signer).
Only then connect a source-controlled prospective collector, initially
without odds or actionable recommendations. Require a second independent
review before allowing verified records into research evaluation.

**Production recommendations remain DISABLED. No EV, ROI or betting advantage
is claimed.**
