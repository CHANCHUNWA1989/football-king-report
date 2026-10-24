# Prematch phase 10 — production release acceptance

This is a **research-only** checklist. Passing GitHub Actions does not authorize real-money recommendations. Do not commit provider API secrets, signing private keys, TSA credentials or genuine customer data.

## Genuine provider sandbox admission

- [ ] Record the provider's legal name, contracted sandbox hostname, permitted API paths, rate limits and data license.
- [ ] Store credentials only in a protected secret store; require least-privilege, read-only scopes and scheduled rotation.
- [ ] Verify DNS pinning, TLS hostname validation, no redirects, no internal IP destinations and explicit host allowlist.
- [ ] Obtain a provider-generated signed quote receipt; pin its independently authenticated public key, validity interval and revocation policy.
- [ ] Capture raw response, fixture identity, kickoff time, provider capture time, UTC retrieval time, SHA-256, HTTP status and source receipt.
- [ ] Replay captured bytes through the same parser and verify schema, freshness, market mapping, settlement rules and failure behaviour.
- [ ] Execute an authorized **real sandbox** request with credentials supplied by an operator; save redacted evidence and run identifiers. No real request is asserted here.
- [ ] Test 401, 403, 429, 5xx, timeouts, corrupted payloads, DNS changes, revoked keys and expired markets.

## Trusted RFC 3161 timestamp acceptance

- [ ] Select a legally and operationally approved independent TSA and obtain its CA chain via an authenticated channel.
- [ ] Validate certificate path, EKU, revocation policy, algorithm constraints and TSA policy OID.
- [ ] Verify DER response/token signature and message imprint against **exact archived bytes**; verify genTime and allowable skew.
- [ ] Persist the original token and verification transcript with independent immutable retention.
- [ ] Run a genuine independently issued token positive case and altered-payload, forged-root, stale-token and revoked-certificate negative cases.
- [ ] Document how trust roots are rotated, revoked and pinned across deployments.

## Evidence durability and performance

- [ ] Test abrupt termination **during** ledger write, short writes, partial trailing JSONL and power-loss recovery.
- [ ] Independently anchor ledger head hashes; detect truncation to a formerly valid prefix.
- [ ] Use restricted storage permissions, safe directory file descriptors, directory fsync and backup restore drills.
- [ ] Run sustained hours-long multi-process stress and measure write latency, retries, lock starvation and orphan archives.
- [ ] Verify evidence hashes and archived bytes after every restore.

## Release freeze / gate

- [ ] Pin the full 40-character commit SHA and preserve a signed, protected release tag.
- [ ] Confirm six required CI checks on that exact SHA, including security and regression checks.
- [ ] Record test coverage, risk owner, reviewer approval, immutable artifacts and rollback instructions.
- [ ] Independently attest sandbox, source identity, TSA trust and held-out prospective predictive performance.
- [ ] Obtain explicit authorized human release approval. **Never infer authorization from caller-supplied booleans.**

Until every independent attestation and prospective performance condition is satisfied: `status=HOLD`, `production_recommendations=DISABLED`.
