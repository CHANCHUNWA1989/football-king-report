# P4 Intelligence-X typed claim corroboration (HOLD)

Stacked on #587; does not duplicate existing final score corroboration or fixture identity engines.
P3 exact head 4b4912c6ab3a281eddf3d5a456f42cb571de4a47: five CI workflows succeeded;
regression job 138419705900 reported 2367 tests, 16 skipped, no failures.
https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45386797993/job/138419705900

Offline diagnostic for externally normalized injury, lineup, red-card and club notice claims.
Requires exact fixture, subject, claim and kind IDs, exact reviewed URL registry, explicit
publisher and origin groups, two payload/excerpt hashes, and bounded UTC clocks.
Repeated sources, common origin or owner, duplicate hashes, conflicting claims and
missing/stale/future clocks block the entire batch. Different hashes are not evidence
of independence, and configuration is not an attestation. No natural-language extraction,
real player or fixture identity resolution, official red-card priority, or rights verification
is performed. An agreement candidate still has independently_verified=false and HOLD.
Firecrawl v2 currently supplies no independently attested upstream clock, so its output
cannot be automatically promoted to an agreement candidate. No live data, secrets, network,
model integration, automated predictions, EV or publication.

15-minute maximum is a conservative research default, not a calibrated live-event SLA.
A future verified ingestion path must bind raw bytes to claim extraction, prove external origin
and upstream clocks, verify identity using existing project gates, and resolve official source
conflicts without overriding HOLD on ambiguous evidence. Test:
PYTHONPATH=ops python -m unittest discover -s ops/tests -p 'test_intelligence_x_claim_corroboration.py' -v
