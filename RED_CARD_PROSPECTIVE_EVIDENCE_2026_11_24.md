# Red-card prospective evidence scaffold — 2026-11-24

Previous head 11162e408744d0b9d806f25ad1b957bba0e6387d: job 138355924771 logs explicitly show all four
CardStress tests OK, including the 648-combination monotonic grid;
2355 ops tests OK (27.765 s), 117 legacy tests OK. These are synthetic
engineering tests, not actual red-card forecasts.

New module ops/red_card_forward_evidence.py accepts normalized authorized
collector bytes; exact fixture/player/side/score/clock agreement and distinct
declared publishers/origins are required. SHA-256 content-addressed local
archive has exclusive writes and replay integrity checks. This is NOT raw
provider authentication, an immutable external archive or proof of source
independence. No live collector or credentials are installed.

The xG development routine differences same-provider/model cumulative
snapshots before, exactly at, and after the card; rejects missing windows,
revisions, mixed models and post-cutoff inputs. Pooled per-second ratios
are descriptive, not causal or validated. Exact boundaries are deliberately
strict; sources lacking them stay excluded. Future work: fit by league,
score, card time and strength with independent development data; establish
externally witnessed model manifest and predictions before scoring.

Prospective intake binds prediction to both event input hashes, excludes
development fixtures, checks declared chronological order and final score
consistency; never treats caller flags or local hashes as proof of time or
publisher authenticity. It returns zero verified samples until an actual
source-specific external capture witness and independent final result
verifier are connected. No true prospective red-card data was obtained
in this change. No production integration or promotion; HOLD / DISABLED.

Run: python -m unittest ops.tests.test_red_card_forward_evidence -v
New test execution must be verified on this head independently.
