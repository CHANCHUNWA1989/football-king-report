# D pilot capacity incident: 2026-11-28 (research only)

Failed run 46130358395, job 140934214234, checkout
38b03aaf09a64f5b1fa0212c63edce09fa9f3fa9. The 65 prior unit tests
and signed artifact download succeeded. The compound shell step exited 1
without printing which command failed. The preparation JSON was redirected.

The exact checkout has 8 October and 24 November archive directories within
the registered run range before the current run, excluding older archives.
The original result-blind catalogue rejects 32 historical captures against
MAX_HISTORY_CAPTURES=31, before any proof read or API request. With one
current proof this is 33 versus the total bound of 32. This is a reproducible
blocking condition, not proof that no other rejection occurred.

New preflight emits bounded aggregate counts and fails closed on overflow.
The accompanying test reproduces the original collect rejection against
the actual checked-in catalogue, with reads and provider metadata forbidden.
No archived evidence is removed, sampled, or overwritten; no limits raised.
No new live workflow, rerun, provider calls, promotion, or deployment.

Next design: a separately reviewed, bounded segmented verification scheme
with a fixed full catalogue digest, per-segment provenance, complete coverage,
cross-segment deduplication and conflict quarantine. Do not merge partial
scores or select the latest 31. Resource benchmarks and trust-preserving
aggregation are prerequisites; genuine authenticated results remain absent.

The historical model C evidence is a separate concern. Existing 1958-case
historical replay shows modest aggregate improvements (hits 990 to 1008,
log loss 1.0145297344 to 1.0014796117, Brier .6077112287 to .5982791269).
No paired per-fixture losses or outcome vectors were retrieved for that
replay, so a paired confidence interval cannot be reconstructed from aggregates.
Latest observed C audit: 392 candidate observations, 0 exact two-publisher
scores, 0 authenticated forward samples. HOLD/DISABLED remains mandatory.
