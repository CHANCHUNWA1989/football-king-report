# Phase 11 — acceptance evidence and remaining blockers

**No live provider, independent TSA, real outcomes, or positive EV are claimed.**
All production decisions remain HOLD / DISABLED.

## Real sandbox evidence
- [ ] Operator provides licensed provider name, allowed HTTPS sandbox host, read-only secret reference, consent and fixture schema.
- [ ] Authorized connection verifies DNS/TLS pinning, no redirects, bounded retries, 401/403/429/5xx handling, signed receipt and archive replay.
- [ ] Preserve independently authenticated provider key and provider-generated source signature. A local synthetic transport test is not a real sandbox acceptance.

## RFC3161 timestamp
- [ ] Independent TSA identity, certificate chain, revocation evidence, policy OID, and trusted clock are authenticated out of band.
- [ ] Verify real DER token signature, imprint and genTime against the exact archived response. Preserve original token and verification transcript.
- [ ] Test invalid imprint, forged CA, expired/revoked TSA and malformed tokens. Passing locally supplied CA roots does not prove independent trust.

## Crash and power loss
- [ ] Fault inject at pre-append, mid-write, post-write, fsync and directory-fsync boundaries.
- [ ] Restore partial trailing ledger records only under a documented operator recovery protocol; do not silently truncate evidence.
- [ ] Externally anchor ledger heads and test valid-prefix truncation, orphan archives and backup restore.
- [ ] Run sustained multi-hour stress outside short CI timeouts and record resource usage and lock contention.

## Walk-forward / positive EV
- [ ] Obtain source-verified, timestamped historical odds and actual results, with frozen fixture IDs and settlement rules.
- [ ] Enforce chronological train/calibrate/test boundaries and purging; prove no lookahead or data leakage.
- [ ] Publish sample sizes, Brier/log loss, calibration, baseline comparison, uncertainty, and cost-adjusted EV with confidence intervals.
- [ ] Forward paper-trade evaluation with market latency, limits, slippage, commission and missing-odds handling.
- [ ] A high numeric EV or positive paper result is not by itself evidence of production readiness.

## Release authorization
- [ ] Confirm all six CI checks for the exact commit SHA and independently signed release manifest.
- [ ] Obtain independent provider, TSA, held-out performance and sandbox attestations plus human approval.
- [ ] Keep `production_recommendations=DISABLED` until evidence is independently verified.
