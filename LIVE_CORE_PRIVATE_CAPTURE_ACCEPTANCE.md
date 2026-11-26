# LIVE-CORE real-capture acceptance checkpoint

Private operator command: python ops/live_core_private_capture_runner.py /private/capture
The directory contains manifest.json, api-football.json, sportmonks.json.
The schema is demonstrated by ops/tests/test_live_core_private_capture_runner.py;
the test is fabricated and may never count as actual provider evidence.

Keep raw data, private quotes and credentials out of Git and CI artifacts.
Use only captures permitted by the actual provider plan and data agreement.
The manifest records original byte SHA-256, canonical mapping, both clocks,
decision epoch, frozen prematch prior, requested full-time market definitions,
optional quote claims and operator confirmation of capture rights. A local
manifest is not externally witnessed and the runner is historical research only.
It cannot authenticate a source or certify an executable quote.

Real acquisition still requires a dedicated authorized account, actual quota
and entitlement evidence, shared accounting across all consumers, and an
approved transport; the repository's existing simulated reservation does not
authorize any HTTP call. No secret-enabled workflow added. Existing public
research in #655 has four pre-kickoff signed native fixture candidates but no
live xG/red-card/quote cohort. Do not conflate the two evidence types.
StatsBomb Open Data is a potential separate historical research source, subject
to its agreement, not a live Liga MX source: https://github.com/hudl/open-data .
No raw data copied here and no provider subscription or permission presumed.

Acceptance: exact-head CI; then private real-capture run with both native
payloads and reliable as-of clocks; record redacted reason codes and evidence
digests. Only separately authenticated forward evidence and calibration may
support future promotion. HOLD/DISABLED.
