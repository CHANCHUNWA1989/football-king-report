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

## P0-7 — vendor contact pack (2026-11-06)

**Status: WAITING_PROVIDER — drafts prepared, NOT sent.** The owner must initiate contact; no reply, permission, purchase, API key or sample acquisition is claimed. Reuses P0-5; only public contact and terms pages were checked, using ordinary HTTPS without paid research APIs. Original licensed data must stay out of this public repository.

### Contact routes and newly checked restrictions

| Priority | Provider / published channel | Targeted evidence checked on 2026-11-06 |
|---|---|---|
| 1 | **TheStatsAPI** — **support@thestatsapi.com**, published General enquiries link on [official Contact](https://www.thestatsapi.com/contact); the public email-protection link decodes to this address. | [Terms, “Data usage” and “Termination”](https://www.thestatsapi.com/terms), page dated 2026-04-01: storage is limited to what is reasonably necessary to operate the application; data access/use ends on termination. Obtain an explicit written archival/reuse exception or an agreed sufficient retention scope. Commercial-use/AI-builder advertising does not settle ML-training rights. |
| 2 | **Footiqo** — [official contact form](https://footiqo.com/contact/); paste the draft below. No unmasked email was verified, so none is inferred. | [Dataset Licence §§2–6, 9–10](https://footiqo.com/dataset-licence/), page dated 2026-10-08: legitimately downloaded files permit private non-commercial research/ML and retention after updates expire, subject to third-party rights. No public API; automated dataset downloads/exports need separate written permission. Commercial/public use needs scope confirmation. |

Known product research above is reused. Footiqo's [product page](https://footiqo.com/premium/premium-football-database/) advertises historical opening/closing odds; Asian handicap/totals coverage and actual quote timestamps remain unconfirmed. No new prices, quota or historical completeness are asserted. No sample/export/API endpoint was accessed.

### Draft 1 — TheStatsAPI (email; do not send automatically)

To: support@thestatsapi.com
Subject: Written licence and timestamped Asian odds sample — Football King V

Hello TheStatsAPI team,

We are preparing Football King V for internal AI/ML research and chronological out-of-sample validation. Recommendations and betting execution remain disabled. Before subscribing or accessing data, please confirm in writing:

- Permission for automated API retrieval, AI/ML training, backtesting and internal derived models; any restrictions on commercial use or publishing aggregate evaluation metrics.
- Raw per-bookmaker pre-match Asian handicap and goal-total quotes, including quarter lines, selections, decimal prices, stable event/bookmaker IDs and UTC kickoff.
- Actual per-quote bookmaker-update and original provider-capture UTC timestamps, their precision/meaning and historical archival provenance; opening/closing labels alone are insufficient.
- Available leagues, seasons, bookmakers and quote history, including gaps, corrections, voids and whether displayed prices were available to customers.
- Permission to retain original bytes, hashes, private models and derived results for reproducibility, including after cancellation; please clarify your storage and termination clauses.
- The applicable plan, total fees/currency/taxes, quotas/rate limits, and a no-obligation free raw sample with its own written usage permission and schema.

Please identify the licensing entity, applicable terms/version and any upstream restrictions. We are requesting information, not ordering a service.

Regards,
[Owner name / organisation]
[Owner reply email]

### Draft 2 — Footiqo (contact-form message; do not submit automatically)

Subject: Written data licence and Asian odds coverage enquiry — Football King V

Hello Footiqo team,

We are evaluating your historical datasets as a backup for Football King V's internal AI/ML research and chronological out-of-sample validation. Recommendations and betting execution remain disabled. Please confirm in writing:

- The product/licence covering AI/ML training, backtesting and retained private models, plus commercial-use and aggregate-publication limits.
- Raw per-bookmaker Asian handicap and goal-total odds, including quarter lines, selections, decimal prices, stable event/bookmaker IDs and UTC kickoff; please state explicitly if these markets are unavailable.
- Genuine per-quote update/original capture UTC timestamps and archival provenance, rather than only opening/closing columns or export-generation dates.
- Exact seasons/leagues/bookmakers, history granularity, gaps, corrections, void rules and historical price-availability evidence.
- Permitted original-file storage, retention and reuse after updates end, with any upstream restrictions.
- Prices/currency/taxes, a no-obligation free representative raw sample and usage permission, plus download/update quotas and delivery options.

Your policy says there is no public API and automated downloads require written approval. Can you authorise an automated delivery route, or only manual downloads followed by permitted local processing? We will not scrape or automate downloads without approval. This is an enquiry, not an order.

Regards,
[Owner name / organisation]
[Owner reply email]

### Written-reply acceptance table

Record separately for each provider/product/plan. Each row starts **PENDING**; store the dated original reply/contract privately and record its immutable reference/hash, exact clause, reviewer and decision reason. A supplier's “yes” without scoped evidence cannot set PASS.

| ID | Required written confirmation / evidence to check | Failure or follow-up trigger | TheStatsAPI | Footiqo |
|---|---|---|---|---|
| R01 | Identifiable licensing entity and authorised reply; product/plan/terms version; permission for this project's automated local processing and AI/ML training/backtests, with an explicitly authorised acquisition method (API, approved automatic delivery or manual files), derived models and intended publication/commercial scope; upstream rights or exclusions stated. | Marketing copy, credentials or “AI friendly” alone; intended use excluded or signatory/rights unresolved. | PENDING | PENDING |
| R02 | Both raw **Asian handicap + goal totals**, per bookmaker; native event/bookmaker IDs, market, selection, signed quarter line, decimal odds, competition/kickoff; price availability and suspension/void/correction semantics. | 1X2 consensus, inferred odds, missing market, synthetic prices or no availability evidence. | PENDING | PENDING |
| R03 | Real per-quote UTC bookmaker update + original provider capture/archive times, precision and immutable source receipts; update <= capture < kickoff. Preserve actual new download/receipt time separately; never backdate it. | Opening/closing label, export date or caller timestamp substituted for historical capture; no authentic pre-match custody. | PENDING | PENDING |
| R04 | Explicit league/season/bookmaker/market coverage matrix, date range, sampling frequency, missingness, revisions and opening/closing availability. Lock intended cohort before results analysis. | General “10 years”/“since 2015” claim without market-level coverage; revised history cannot be distinguished. | PENDING | PENDING |
| R05 | Written raw-byte storage/retention duration and deletion duties, reuse/derived-model rights after expiry/cancellation; private audit/reproduction and aggregate publication scope sufficient for the owner's declared study. | TheStatsAPI default termination/cache restriction unresolved; resale/public raw-data rights assumed; retention insufficient. | PENDING | PENDING |
| R06 | Quoted plan, complete fees/currency/taxes/renewal, quotas/rate limits/history/export limits, delivery mode, and explicit no-obligation free-sample rights. State “no API” or “manual only” when applicable. | Purchase/trial/card/key required without separate owner approval; unspecified limits; automatic acquisition unlicensed. Manual-file permission qualifies only that scope, never an automated feed. | PENDING | PENDING |
| R07 | Representative **real**, explicitly authorised original sample + schema/source/rights references proving R02–R04, inspected independently with existing input contract. One event checks format only. | Sample unavailable, masked/synthetic/missing fields, contradictory rights or undocumented adapter compatibility. Do not download before permission. | PENDING | PENDING |

Decision rules for later automation (specification only; no new code):
- Allowed row states: PENDING / PASS / FAIL. Missing, ambiguous, conflicting or unverified evidence remains PENDING; an explicit incompatible restriction is FAIL. Scope-restricted permissions cannot silently become broader permissions.
- Current pack state is WAITING_PROVIDER. A complete reply may become READY_FOR_SAMPLE_REVIEW only after independent human verification of R01–R06 and explicit sample-access permission; no automated contact, download, purchase or key creation follows from this label.
- Mark DATA_QUALIFIED_FOR_DECLARED_SCOPE only when R01–R07 all PASS and the actual originals satisfy the existing capture/import/provenance gates. Any FAIL => NOT_QUALIFIED for that scope; any PENDING => WAITING_PROVIDER with one consolidated clarification list, then stop.
- Even qualified odds cannot supply missing genuinely pre-match frozen forecasts/training cutoffs or independent FT90 results/identity bridge. These remain separate #452 requirements; a vendor's own result feed is not automatically independent.
- No table result closes #452/#439, proves positive EV, releases #451 or changes HOLD/DISABLED. No predictive/profitability improvement is established.

### Owner action and stop point

Fill in the two sender fields. Send Draft 1 manually through your own email; keep Draft 2 ready for the Footiqo form if the priority provider cannot satisfy the requirements. Request a written reply addressing R01–R07 and retain it in the existing authorised private archive, with no keys/commercial originals in GitHub or chat. No message was sent or form submitted in P0-7.

Next executable step: assess that new written reply against this table; only after explicit permission arrange an authorised sample review. Until then **WAITING_PROVIDER — STOP**, no polling, repeated vendor research or test runs. Single Codex; documentation-only update to the existing memo; no QA/Data/Quant agent, paid service, purchase, API key, odds download, merge, deployment or betting activation. #451 remains Draft; **HOLD/DISABLED; POSITIVE_EV_VERIFIED=False**.
