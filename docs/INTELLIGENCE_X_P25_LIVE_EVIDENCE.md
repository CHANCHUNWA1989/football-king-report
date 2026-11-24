# P25 live evidence qualification (HOLD)
Review date: 2026-11-24 (HKT). No live ingestion or deployment enabled.

## Public documentation reviewed
- OpenLigaDB data license (updated 2026-11-07): https://www.openligadb.de/en/license
  ODbL 1.0, attribution and applicable share-alike obligations; community-entered data without editorial review or accuracy/timeliness warranty. Third-party imagery excluded. No proof of independent collection for a particular Bundesliga fixture. English translation is not authoritative; German terms and use scope require review before approval.
- API terms (updated 2026-11-07): https://www.openligadb.de/en/terms-of-use
  Central caching, change-date polling, live requests at most once every 30–60 seconds per league, jitter and backoff. Meaningful user agent/contact. Treat as a candidate, not an approved connector. A public API data retrieval attempt in the research environment was unsuccessful; no real capture retained.
- football-data.org: https://www.football-data.org/pricing ; https://www.football-data.org/about ; https://docs.football-data.org/general/v4/policies.html
  Free scores are delayed; live-score plan listed at EUR 12/month and lineup/card plan at EUR 29/month, subject to terms/tax. No subscription or credentials acquired. No evidence of independent origin versus OpenLigaDB for a specific match.
- Historical research candidate: https://github.com/hudl/open-data (StatsBomb open data; selected competitions/seasons and separate license). Not a live xG feed.

## Implemented
Offline audit of 2–8 normalized observations; requires explicit score and on-pitch dismissal counts, regulation phase, mapped fixture IDs, upstream and observation UTC clocks, distinct publisher/origin labels and supplied SHA256 digests. Maximum age 120s, pairwise skew 60s; conservative research thresholds not calibrated against real feeds. Any malformed, stale, conflicting or duplicate input blocks the batch. Equal state is only AGREEMENT_CANDIDATE; no source approval or scoring authorization. Hashes and group labels are supplied, not independently authenticated. No official red-card identity verification, live xG, odds, raw archive, or scheduler integration.

## Validation
Local Python 3.13.5: 10/10 new synthetic tests passed (0.001s); exact file blobs 4f8bbfce8c592b471916489eae22347ebcb62edc and f6a802dcf80244976193b7d6fb4a8f88d7cea1fc; existing parser blob d1dae7ddd8d176a31516dfc5733dd0e1c6aa8468.
No real match evidence, full regression, or production readiness claim. Keep existing source policy unchanged until scoped review and approval. Next: acquire authorized independent sources and retain real timestamps/raw evidence; validate coverage and latency; connect only to research quarantine. HOLD/DISABLED.
