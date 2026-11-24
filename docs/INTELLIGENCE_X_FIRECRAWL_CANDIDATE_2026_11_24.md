# Intelligence-X / Firecrawl offline candidate seam (2026-11-24 HKT)

Status: HOLD; production_recommendations=DISABLED. No live endpoint, SDK, credentials,
new dependency, background job, public payload archive, or model connection is added.

## Integration decision
- Existing SoccerData/penaltyblog research: [#458](https://github.com/CHANCHUNWA1989/football-king-report/pull/458) and [#470](https://github.com/CHANCHUNWA1989/football-king-report/pull/470); do not duplicate it.
- Existing rights blockers: #551 and #554; shared HTTP security work: #578. This seam does not bypass them.
- Upstream project: https://github.com/firecrawl/firecrawl (AGPL-3.0 per GitHub metadata).
  Using a hosted API versus deploying or modifying upstream software requires separate terms/license review.
  A collector is not a second independent publisher, and its timestamp is not an upstream observation timestamp.
- This is a local normalized input contract, not a validated Firecrawl wire format. It only accepts
  preloaded synthetic or separately lawfully acquired bytes, exact reviewed URLs, HTTP 200,
  timezone-aware collection times and bounded payloads. It hashes supplied bytes without outputting the body.
  A reviewed URL does not grant rights, the payload hash does not prove publisher origin,
  and a claimed upstream timestamp remains unverified. No scoring or trading/betting integration.

## Offline test command
`PYTHONPATH=ops python -m unittest discover -s ops/tests -p 'test_intelligence_x_firecrawl_candidate.py' -v`

## Before any real pilot
1. Review target publisher terms, API contract, retention and exact intended use; record independent evidence privately.
2. Verify actual Firecrawl API schema and no-redirect/destination control, credential handling, quota and costs.
3. Prove publisher origin, stable fixture identity, independently sourced corroboration and observation time.
4. Test stale/ambiguous/duplicate/conflicting records with zero promotion on failure, then isolated forward validation.
5. Require independent review and separate authorization before any real collection or production connection.

No source grant, real upstream data, external timestamp attestation or improvement in forecast accuracy is asserted.
