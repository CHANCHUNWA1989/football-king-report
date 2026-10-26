# Football King AI — Phase 10 release audit and acceptance checklist

**Scope:** Phases 1–9 prematch odds research path. This is a research readiness checklist, not a production release certification.

## Verified baseline
- Phase 9 commit: `36fc37843b8c6d37363febda78468ca79b10b9b0`
- Six GitHub Actions workflows completed successfully for that commit.
- Code paths include bounded HTTPS retrieval, host allowlisting, public-IP DNS pinning, archived raw responses, SHA-256 replay, chained evidence, key-bound receipts, RFC3161 verification interface, and subprocess stress tests.
- Test success proves the tested cases only; no provider connectivity or predictive edge is established.

## Live provider sandbox — must be completed before acceptance
- [ ] Record real provider legal name, approved sandbox hostname, contract, quota, and response schema; do not commit credentials.
- [ ] Configure the approved hostname allowlist and credential environment variable in restricted secrets storage.
- [ ] Confirm outbound DNS resolves only globally routable addresses and TLS certificate validates the original hostname; prohibit redirects and proxies that bypass pinning.
- [ ] Verify real fixture/team IDs, kickoff and capture chronology, odds market, overround, rate-limit handling, timeout and credential redaction.
- [ ] Archive exact HTTP response bytes; independently replay SHA-256, ledger chain, and signed receipt.
- [ ] Execute live sandbox positive, malformed response, expired quote, unauthorized, 429, 5xx, redirect and DNS rebinding tests; retain non-secret logs.
- [ ] Obtain explicit provider approval before production traffic.

## RFC3161 / source trust — must be completed
- [ ] Independently provision and pin real provider public keys; document rotation, expiry and revocation.
- [ ] Independently provision genuine TSA root chain, certificate policy and revocation validation requirements.
- [ ] Verify DER timestamp token signature, imprint, signer chain, signing time, algorithm and acceptable clock skew.
- [ ] Bind timestamp evidence to the precise archived bytes or receipt; test wrong imprint, expired TSA cert and revoked signer.
- [ ] Independently validate receipt issuer identity and capture chronology.
- [ ] Archive signed acceptance artifacts with an externally retained, tamper-resistant anchor.

## Release and version freeze
- [ ] Pin full 40-character Git commit and dependency lock or digest.
- [ ] All six required CI checks must be green on **the same commit**.
- [ ] Run extended concurrency, process kill during append, crash recovery and partial-ledger fault injection.
- [ ] Verify archive inventory, no orphan responses, full replay, permissions, symlink/path attacks and ledger integrity.
- [ ] Independently reproduce held-out calibration, EV and baseline comparisons without leakage; document sample sizes and uncertainty.
- [ ] Have an authorized reviewer approve provider, timestamp, security, legal and model evidence.
- [ ] Only after independent acceptance consider a separate, reviewed production-enable change. Current gate **always returns HOLD**.

## Known residual risks
- Local hash chains are not immutable and have no external integrity anchor.
- Receipt and timestamp validation interfaces are not proof of a real trusted provider or TSA.
- Cross-process tests are bounded; sustained soak testing, power-loss simulation and distributed storage semantics remain unverified.
- Release manifest digest is local integrity metadata, not a signature.
- No real provider sandbox account, keys, endpoints, or trustworthy timestamps have been supplied.
