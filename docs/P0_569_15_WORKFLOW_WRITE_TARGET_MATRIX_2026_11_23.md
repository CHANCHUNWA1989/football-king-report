# P0 #569 — 15 write-capable workflow target matrix and migration order

**Date: 2026-11-23 HKT. Evidence: pinned `main` `3ce493fbeb9bfea29af1b93064a085afe8efb280`. Draft PR #571 research only; HOLD / DISABLED.**

## Method and limits

Read actual source of all **15 workflows** previously identified with `contents: write` in the 63-file fleet scan. Extracted each workflow's `on` events, write-capable job, literal Git push or `gh api -X PUT` commands, target/path variables, and where applicable the existing archive helper implementation. No workflow, `main`, remote branch, credential, GitHub Ruleset, or site was changed.

**Classification is static and time-pinned, not a live write audit.** GitHub Contents API calls below have no explicit `branch` field in their observed requests; the API normally targets the repository default branch, which is `main` at the pinned observation. Those are **potential default-main mutations** until validated against actual run/token and branch evidence. `contents: write` alone is not proof of a successful write. The target matrix cannot discover indirect Python, reusable/composite Actions, external GitHub App, or other out-of-band writers.

## Reviewed target matrix — all 15

| # | Workflow | Write-capable job and mechanism | Confirmed code-defined target(s) | Trigger/priority | Cutover obligation |
|---|---|---|---|---|---|
| 1 | `football-king-asia-apis.yml` | `archive`; Contents API PUT | `sources/asia_api_latest.json` | dispatch / push main / scheduled; P0-B | preserve latest research metadata and dependent mobile source visibility |
| 2 | `football-king-bsd-free.yml` | `archive`; Contents API PUT | `sources/bsd_history/YYYY/MM/DD/RUN-ATTEMPT.json.gz`, `sources/bsd_status_latest.json`; conditional `sources/bsd_market_latest.json` | dispatch / push main / scheduled; P0-B | keep history plus status/market independent; only update market when source passes guard |
| 3 | `football-king-german-live.yml` | `archive`; Contents API PUT | `sources/live_germany/history/YYYY/MM/DD/HH-RUN.json.gz`, `sources/live_germany_latest.json` | dispatch / push main / hourly schedule; P0-B | preserve time validity, hourly history, stale-update guard and iPhone feed |
| 4 | `football-king-hkjc-free-research.yml` | `archive`; Contents API PUT | `sources/hkjc_tipsme_free_latest.json` | dispatch / push main / scheduled; P0-B | preserve guarded research-only metadata; never imply official HKJC odds authorization |
| 5 | `football-king-iphone.yml` | `archive_provenance` and `archive`; **two Git pushes to main** plus Contents API PUT | `forecast_provenance/YYYY/MM/DD/RUN-ATTEMPT/*`; `history/`, `shadow/`, `research_pairs/`, optionally `worldwide_shadow/`, `verification_slates/`; `evidence/settled.json` | dispatch / workflow_run / push main / scheduled; **P0-A** | dual writer migration; preserve old 105+ research samples, two-view site read parity and historical bytes |
| 6 | `football-king-japan-free-market.yml` | `archive`; Contents API PUT | `market/japan_free_status.json` | dispatch / scheduled; P0-B | keep source status and iPhone J1 metadata without treating as executable licensed quotes |
| 7 | `football-king-odds.yml` | `archive`; Contents API PUT | `market/history/YYYY/MM/DD/RUN-ATTEMPT.json.gz`, `market/collection_status.json`, conditional `market/latest.json` | dispatch / scheduled; **P0-B** | separate historical archive, quota status and latest snapshot; preserve stale/valid-quote guard and consumer path |
| 8 | `football-king-research-extensions.yml` | `archive`; Contents API PUT | `sources/research_extensions_history/YYYY/MM/DD/RUN-ATTEMPT.json.gz`, `sources/research_extensions_latest.json` | dispatch / push main / scheduled; P0-B | preserve history + latest compatibility for iPhone overlay |
| 9 | `football-king-secondary-sources.yml` | `archive`; Contents API PUT | `sources/history/YYYY/MM/DD/RUN-ATTEMPT.json.gz`, `sources/latest.json` | dispatch / push main / scheduled; **P0-B** | preserve result/fixture history and `sources/latest.json` iPhone consumers |
| 10 | `football-king-six-free-upgrade.yml` | `archive`; Contents API PUT | `sources/six_league_quality_history/YYYY/MM/DD/RUN-ATTEMPT/{six-free,seven-gates,fixture-overlap}.json.gz`; `sources/six_league_free_latest.json`, `sources/seven_quality_gates_latest.json`, `sources/six_league_fixture_overlap_latest.json` | dispatch / push main / scheduled; **P0-B** | archive all three evidence streams; preserve seven-gate/mobile readiness read compatibility |
| 11 | `football-king-weather.yml` | `archive`; Contents API PUT | `sources/weather_history/YYYY/MM/DD/RUN-ATTEMPT.json.gz`, `sources/weather_latest.json` | dispatch / push main / scheduled; P0-B | maintain weather history and freshness validation; weather must remain context, not automatically a scoring input |
| 12 | `football-king-weekly.yml` | `weekly-report`; Contents API PUT | `reports/weekly/REPORT_DAY.md` | dispatch / push main / Friday schedule; P0-C | use a reviewed PR/report artifact or independently approved read route; preserve old reports |
| 13 | `football-king-wide-free.yml` | `archive`; Contents API PUT | `sources/wide/history/YYYY/MM/DD/RUN-ATTEMPT.json.gz`, `sources/wide_latest.json` | dispatch / push main / scheduled; P0-B | preserve worldwide research history and iPhone global league overlay |
| 14 | `private-all-market-research.yml` | `archive_redacted_coverage`; Contents API PUT | `market/private_summary_latest.json` | dispatch / push main / scheduled; **P0-B** | maintain strictly redacted public-only counts; never copy private feed payload into public Git |
| 15 | `four-model-shadow-daily.yml` | `archive_ndr_capture` and `archive_openliga_capture`; **two Git pushes to main** | `ndr_capture_provenance/YYYY/MM/DD/RUN-ATTEMPT/*`, `openliga_capture_provenance/YYYY/MM/DD/RUN-ATTEMPT/*` | dispatch / scheduled; **P0-A** | isolate both signed-evidence preservation jobs and audit trusted source identity; no main bot bypass |

**Source path evidence:** target strings/assignments occur directly in the pinned 15 workflows. The five `archive_prepare.py` path families in row 5 and two capture family names in row 15 were additionally read from their actual helper modules; no names are invented. The 15 workflows represent **at least 17 write-permission job blocks** (two each in rows 5 and 15, one in each of the other 13).

## Verified concrete read-dependency split

Current `football-king-iphone.yml` reads `sources/latest.json`, BSD status and market, `sources/weather_latest.json`, `sources/wide_latest.json`, `sources/research_extensions_latest.json`, `market/private_summary_latest.json`, `market/japan_free_status.json`, `market/latest.json`, and `sources/seven_quality_gates_latest.json` in named build steps / push paths. Its official-readiness panel still reads `main:evidence/settled.json`, while the daily scorecard uses the run-scoped `$RUNNER_TEMP/settled.json`. New research-only shared-evidence preview is not a deployed consumer migration.

Not all 15 producer outputs have a verified iPhone consumer. A missing mention in this one workflow is **not** evidence of no other consumer; all public, Pages, mobile, historical and script readers require separate inventory.

## Safe migration sequence — no automatic execution

1. **P0-A immutable archival writes:** Independent reviewers inspect `football-king-iphone.yml` and `four-model-shadow-daily.yml` together, ensure fixed isolated archive refs/permissions, no force push, byte-preserving replay/collision rejection and full legacy continuity. No live archive branch has been provisioned or canary tested.
2. **P0-B live metadata + history writers:** Treat immutable historical batches separately from mutable latest/status pointers. Review all 12 producers in P0-B, use an approved isolated branch/object store for immutable data and an explicit validated site-read/manifest strategy for current snapshots. Avoid naive branch switches that would strand mobile readers or change staleness semantics.
3. **P0-C weekly reports:** Move report publishing to an approved PR/artifact/isolated reporting route while retaining historical links.
4. **Full read-parity acceptance:** Pin source commit & archive head, reproduce report output/identities from old and new inputs, verify every archived research case and current mobile view; assert old `main` SHA remains unchanged in separately authorized remote synthetic tests. Historical `evidence/settled.json` PUT five-retry failure status remains **UNKNOWN** until redacted, authorized capture.
5. **Independent review / governance:** Require a nonauthor code reviewer and administrator-approved, non-bypass Ruleset proposal only after **every** direct-main write is either migrated or explicitly disabled with verified non-loss behavior. Do not add an unconditional bot bypass.

## Non-release acceptance

- This matrix is **manual source review anchored to one exact `main` SHA**, not an exhaustive repository or network audit, not evidence of successful remote writes, provider licensing, real xG, validated odds or positive EV.
- `#569` / `#439` / `#452` remain open. PR #571 is research Draft/unmerged with 0 independent reviews at this check. No authorized real remote archive branch found.
- **Ruleset activation authorized: false. Production recommendations: DISABLED.**
