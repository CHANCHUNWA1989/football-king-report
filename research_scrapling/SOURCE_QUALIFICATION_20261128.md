# Scrapling source qualification — 2026-11-28

Status: HOLD. production_recommendations=DISABLED; live_trading=DISABLED; model_input_allowed=false.
This is a documented source-policy review, not a grant of live collection or a change to the approved registry.

## OpenLigaDB
- Official data licence: https://www.openligadb.de/en/license (updated 2026-11-07). ODbL 1.0 permits reuse subject to attribution, share-alike for distributed modified databases, and no incompatible technical restrictions. Third-party images and marks are excluded.
- API terms: https://www.openligadb.de/en/terms-of-use (updated 2026-11-07; German original authoritative). Community-maintained entries lack editorial verification; live latency and accuracy are not guaranteed.
- Before any prospective adapter: one centralized per-league cache; use getlastchangedate before downloading changed data; choose at least 60 seconds between requests per league during matches, much less frequently outside matches; jitter, exponential backoff on 429/5xx, meaningful application User-Agent and operator contact. Count requests across all workers; no immediate retries. Current historical qualification is not a compliant continuous polling implementation.
- Provider states user-entered data with no imported third-party databases; this is not independent evidence of where each contributor obtained scores. No public immutable historical snapshots.
- Scope: candidate for delayed research fixture/result metadata, not verified in-play, xG or odds.

## OpenFootball
- https://github.com/openfootball/football.json and https://github.com/openfootball/football.json/blob/master/LICENSE.md declare public-domain/CC0 fixture and results data. Repo update cadence is not a live-feed SLA; no independently certified collection chain or point-in-time availability.
- Candidate for historical corroboration only. Preserve licence and source revision identifiers; no proof that an agreeing score is independently collected.

## Acceptance gate
No change to ops/policies/result_sources_v1.json, disabled.json, or runtime allowlists. Retain #435 prospective seal and preregistered OOS design as unmerged research dependency.
Before actual prospective collection: approved scoped source and documented terms compliance, independently substantiated upstream chain, measured latency and fixture identity, trusted capture/availability timestamps and external witness, no future information, and independently reviewed configuration. Real xG and executable Asian odds remain unqualified. Seven historical matches are not forward samples.
No new data requests, scheduled jobs, raw-content publication, deployment, or production activation in this change.
