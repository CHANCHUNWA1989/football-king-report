# 全球賽事擴展：實際覆蓋範圍與安全分級

This expansion discovers fixtures worldwide via an isolated public-source
candidate adapter. Provider documentation advertises 120+ competitions, but
**only returned, schema-validated, UTC-timed fixtures** are counted. No source
is assumed live or licensed for wagering simply because its website says so.

- Existing OpenFootball/OpenLigaDB wide-league collector remains unchanged.
- New `ops/global_fixture_discovery.py` discovers UTC-timed matches for two
  calendar days from OpenFoot API. A failed network request or unexpected schema
  returns HOLD/zero coverage, never invented games.
- New `football-king-global-discovery.yml` runs every six hours, uploading
  a seven-day research artifact; it does not mutate the production report.
- Duplicate provider match IDs, unzoned kickoff timestamps, malformed teams,
  impossible dates, or fabricated league coverage are rejected.
- Source is **not** independently cross-verified, and has no executable odds,
  independently calibrated model, verified positive EV or staking logic.
- New leagues need separate verified time-point history, stable team identities,
  enough settled results, market quote coverage, and out-of-sample calibration
  before they can join prediction or positive-EV recommendation engines.

Expansion is staged: **fixture discovery → independent confirmation → shadow
model → calibrated EV validation → separately authorized recommendations**.
Production betting remains DISABLED. Never infer that the discovery feed itself
covers all global fixtures.
