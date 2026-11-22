# Agent Reach Data Bridge V1 — Phase 1 (quarantine only)

**Scope:** Offline intake of manually exported public research notes for Football-King and a planned separate Hong Kong horse-racing AI. This stage does not install or call Agent Reach, scrape HKJC, run a model, fetch prices, schedule collection, or publish content. Neither Agent Reach nor this bridge is an authenticated sports feed.

## Input contract

The JSON object has a records array. Each record requires:
- sport: football or horse_racing
- channel: web, github, youtube or rss
- source_type: official_claimed, reporting, community (self-described, NOT authenticated)
- source_url: HTTPS public hostname URL, without query parameters, credentials or fragments
- captured_utc: timezone-aware timestamp, caller supplied and NOT attested
- content: untrusted text, maximum 65,536 characters

Optional fields: event_id (unverified ID label) and published_utc (caller supplied, unverified). The processing clock is also caller supplied. Do not submit session cookies, private links, bookmaker raw prices or unlicensed HKJC data.

All accepted inputs remain QUARANTINE. The output drops raw content and emits only metadata plus a local SHA-256 digest. SHA-256 does NOT authenticate source originality or publication time. Every output has status=HOLD, production_recommendations=DISABLED, agent_reach_executed=false, and zero network requests. All record flags source_authorized, identity_verified, time_attested, eligible_for_model and verified_market_odds are false; verified_positive_ev=null. Same-source same-time exact duplicates collapse; conflicting content rejects the entire batch. Unsafe URLs and contradictory times fail closed.

## Offline usage (Python 3.11+)

Prepare a local JSON file at /tmp/research.json, then run:

    python ops/agent_reach_quarantine.py --input /tmp/research.json --output /tmp/quarantine.json --now-utc 2026-11-22T12:00:00Z
    python -m unittest discover -s ops/tests -p 'test_agent_reach_quarantine.py' -v

Synthetic JSON example, NOT a real match:

    {"records":[{"sport":"football","channel":"web","source_type":"reporting","source_url":"https://example.org/football/report","event_id":"source:fixture-123","published_utc":"2026-11-22T10:00:00Z","captured_utc":"2026-11-22T11:00:00Z","content":"Unverified test article"}]}

## Phase 2 blockers

This change is not wired into any production workflow or model. No external requests, Agent Reach installation, odds quota use, model-weight changes, sealed forecast modifications, EV, stake, or auto-publishing.

Before actual collection: audit Agent Reach upstream connectors and terms, pin and review its release/dependencies, configure a least-privilege read-only runner with explicit network allowlists, keep cookies out of public GitHub, independently verify provider-native event IDs and publisher/time provenance, and keep licensed/private material in private storage. Separately run prospective A/B study and independent review before considering model input for either sport.

CI success here covers synthetic contract tests only; it does not establish real upstream availability, improved accuracy, source independence, positive EV or formal forward-sample eligibility.
