# Provider decision memo — 2026-11-06

Related to issue #452, draft PR #451. Research only; no data downloaded, API connected, subscription purchased or betting enabled.

## Existing official-page research (not re-fetched in P0-5)

The observations below are retained from the earlier assessment; this round does not reverify current prices, rights or access.

1. Football-Data official use policy: https://football-data.co.uk/contact.php
   - Free CSVs are intended for private individuals and academic interest; the site states commercial/AI/model-training requests using automated scraping should assume permission is not granted. At most light twice-weekly automated downloads for permitted personal use.
   - **Decision: do not programmatically ingest into this AI system without explicit permission.**
2. Football-Data historical odds page: https://football-data.co.uk/data
   - Includes Asian handicap and totals in some seasons. Opening and closing columns are not necessarily independently timestamped per quote.
   - Site warns Pinnacle quotes since 2025-07-23 may be systematically stale.
3. TheStatsAPI provider introduction: https://football-data.co.uk/thestatsapi.php
   - Advertises historical/current/opening/closing 1X2, totals and Asian handicap odds and commercial application use; entry subscription advertised from GBP 39/month.
   - **Decision: priority for vendor evaluation only.** Check contract, endpoint response fields, historical depth, capture timestamps, rate limits, permitted storage and AI training before connection.
4. Footiqo data overview: https://football-data.co.uk/footiqo.php
   - Advertises historical AI/backtest datasets from 2015/16 with opening/closing odds where available.
   - **Decision: secondary candidate.** Need quote timestamp granularity and handicap/totals market coverage verified.

## Vendor acceptance checklist

P0-5 review: [#452](https://github.com/CHANCHUNWA1989/football-king-report/issues/452) and [#439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439) remain open. Reviewed existing source assessments, [input contract](p0-1-market-capture.md) and [handoff](codex-low-cost-handoff.md), not private archives or new provider data. Absence below means evidence was not supplied in those reviewed materials; it does not revoke other previously authorized research uses.

| Qualification | Reusable preparation | Required evidence / status |
|---|---|---|
| 1. Written provider authorization | Existing provider candidates and offline adapter | **BLOCKED_EXTERNAL**: independently checkable terms/permission for the selected provider, product, market/season scope, automated AI research, original-byte storage, retention/reuse and publication limits; credentials or advertising are not permission. |
| 2. Actual bookmaker quotes | Existing historical-envelope parser, source/time/identity checks and SHA256 capture | **BLOCKED_EXTERNAL**: original per-bookmaker event/selection/line/decimal price, UTC update and actual receipt times, source reference, late-correction/void rules and price-availability evidence. Public 1X2 consensus is not executable odds. |
| 3. Prospective forecast and training lineage | Existing pre-match capture and frozen join | **BLOCKED_EXTERNAL**: original model/forecast bytes and hashes, model version/run ID, training and outcome-availability cutoffs, independently checkable pre-kickoff custody and event linkage; hashes or caller timestamps alone do not establish this. |
| 4. Independent FT90 outcome | Existing result/identity/provenance guards | **BLOCKED_EXTERNAL**: authoritative regulation-90 final score/status, native event/team IDs with fixed forecast-ID mapping, actual kickoff, publication/receipt UTC times and independently checkable publisher/upstream independence. |
| 5. Reproducible real OOS cohort | Existing import/manifest, chronological holdout, Brier/log loss, calibration and market-comparison tools | **BLOCKED_EXTERNAL**: a common qualified cohort with original source hashes, a locked split/calibration protocol and adequate sample/time/league coverage. Existing unverified research rows and passing synthetic tests cannot establish OOS advantage. |

### Minimum owner-supplied packet

Supply references through the existing authorized private archive; do not put keys or commercial originals in public GitHub/chat. One representative event can check the input contract, not establish an edge.

1. **Rights reference**: provider/product identity and the applicable written terms or permission covering the intended data/AI/storage scope, retention, quota and access limits; no purchase or API key provisioning is requested here.
2. **ODDS + META originals**: one already authorized raw sample with event ID/competition/kickoff, bookmaker, market/selection/line/price, source URL without credentials, provider update/snapshot and actual capture UTC times, plus its rights reference. Reuse the [existing format](p0-1-market-capture.md); another provider requires checking its actual sample before claiming compatibility.
3. **FORECAST + MODEL originals**: the same event's genuinely pre-match frozen forecast/model bytes, version/SHA256, training run and data/result-availability cutoffs, and original custody receipt. If these were never saved, start a separately registered prospective shadow cohort; do not reconstruct historical forecasts.
4. **Independent result original + identity bridge**: the same event's FT90 score/status, source-native event/team IDs, actual kickoff/publication/capture UTC and original provenance/independence receipts. Distinguish regulation, extra time and penalties; do not join by guessed names.

### Release-candidate boundary

Before any holdout results are used to choose a method, lock the selection/split/calibration rules. Then verify the common cohort and compare calibrated probabilities with the same-time market, settlement-based EV/ROI, uncertainty intervals and independently sourced CLV where available. No data-driven threshold tuning or backfill of old A/B/C forecasts.

Only after all five qualifications pass may independent data/quant/safety review assess candidacy. The owner/security admin must also supply #439 branch-protection/no-bypass evidence, independent human review and explicit release approval; this checklist changes no repository protections, trust roots, schedules or recommendation flags.

## Explicit blockers
A vendor's advertised commercial use does not prove that the chosen plan licenses every intended AI training use. Opening/closing odds alone cannot establish a quote-capture timestamp. A vendor feed cannot reconstruct a forecast that the model did not save before kickoff.

**Decision: HOLD / DISABLED; NO PICK (positive EV not demonstrated).** All five evidence checks remain BLOCKED_EXTERNAL. P0-5 changes this checklist only; no provider requests, purchases, new agents, code changes, full-test reruns, merge or deployment. Resume only when new authorized originals or human/security evidence become available.
