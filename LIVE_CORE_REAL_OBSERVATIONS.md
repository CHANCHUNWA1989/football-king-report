# LIVE CORE real-observation research

Run from the repository root: `python ops/live_core_real_observations.py INPUT.json`.
Input has keys a, b, kickoff_utc, prematch, now, markets, optionally xg and previous.
See the acceptance test for the schema. The test fixture is fabricated and must
never be represented as match evidence. No external data acquisition is included.

Each publisher state includes fixture_id, origin, observed/received (UTC epoch
seconds), minute, home/away score, red_home/red_away and phase. Record source
URL without query/fragment and SHA-256 of the original captured payload; the
adapter cannot authenticate or independently check that digest against raw bytes.
Never fabricate a prematch archive or substitute retrospective rates. Missing
xG stays null; conflicting or stale supplied xG blocks the research forecast.
xG is recorded, not fitted or used by the fixed-coefficient challenger.
Only regulation full-time markets are supported; no live quote or EV is certified.

The existing in-play challenger and market engine are reused without changing
their coefficients. Research output always preserves HOLD/DISABLED. Distinct
hostnames and hashes are not proof of publisher independence. The input digest
is a local reproducibility aid, not a signature, external timestamp or ledger.
Provider ingestion/authentication, fixture mapping, raw evidence retention,
same-cut executable odds, prospective calibration and independent deployment
acceptance remain required. No paid requests, credentials, or changes to main.
