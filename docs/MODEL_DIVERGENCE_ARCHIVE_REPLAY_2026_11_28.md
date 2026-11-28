# Offline divergence archive replay (research only)

Fixed source: `shadow/2026/11/28/46130230863-1.json.gz`, Git blob
`a249d3cfe7079f78aadf9c31019ce17ca3efeae6`, 18726 bytes. The repository
shadow archive is not authenticated as a provider source or certified as
an immutable external witness.

`ops/model_divergence_archive.py` checks exact compressed bytes, bounded
decompression and the stored research-only schema. It counts 49 existing
forecast rows and reports zero qualified cross-provider pairs. It does not
recompute a prediction, invent a cutoff or infer an external xG projection.
The mobile candidate is static HTML, read-only and not integrated with Pages.
The report deliberately shows HOLD/DISABLED even if the repository blob matches.

`python -m unittest discover -s ops/tests -p test_model_divergence_archive.py -v`
exercises the actual checked-in archive and negative byte-mutation cases.
No provider calls, new schedules, raw payload publication, main writes,
or production deployment. External source authentication, true xG
derivation, independent review, forward calibration and live site rollout
are still required. Exact-head CI is required before any release claim.
