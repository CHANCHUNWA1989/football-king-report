# LIVE-CORE durable evidence stage

Stacked on #658. The existing combined LIVE CORE provider evidence and xG
assessment workflow includes test_live_core_*.py.

- SQLiteCAS implements the existing quota store contract for concurrent workers
  on one private local filesystem, with explicit initialization, atomic append
  and no silent recreation. Do not use an ephemeral runner or share SQLite over
  an unsupported network filesystem. Cross-host accounting, external revision
  floor, provider quota attestation and exclusive account access remain unmet.
  Reservations remain simulated; no network transport is authorized.
- Sportmonks v3 captured fixture parser expects data object from fixtures/{id}
  with participants, scores, periods and events includes. The source contract:
  https://docs.sportmonks.com/v3/tutorials-and-guides/tutorials/includes/scores
  https://docs.sportmonks.com/v3/tutorials-and-guides/tutorials/includes/periods
  https://docs.sportmonks.com/v3/definitions/types/events
  https://docs.sportmonks.com/v3/definitions/states
  Two raw payloads can now feed the existing research model. Distinct vendors
  do not prove independent upstream feeds or rights. Test payloads are fabricated.
- Sportmonks free scope is Danish Superliga and Scottish Premiership, not Liga MX:
  https://www.sportmonks.com/football-api/free-plan/
  https://www.sportmonks.com/football-api/liga-mx-api/
  No plan change, purchase, credential or API call was made. Verify account
  entitlement and source licensing before a real probe.
- Event revision audit quarantines regressions; neither vendor parser interprets
  unresolved VAR. Even agreeing decreases require event-level review, rather than
  rewriting a previous forecast. The audit is a separate review function, not an
  automatic VAR resolution or a deployed transition store.

Next real acceptance requires authorized captures from both sources, validated
crosswalk and upstream timestamps, shared quota control across all consumers,
event revision policy, frozen prematch archive, prospective sample ledger and
independent calibration. Remain HOLD/DISABLED; no executable quotes or EV claims.
