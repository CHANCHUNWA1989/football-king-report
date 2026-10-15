# Unified AI System Upgrade Audit — 2026-10-16

## Scope
Football, basketball and quantitative finance are separate execution domains. Integration should share a reporting contract, not prediction outputs or credentials.

## Mandatory gates
1. Source provenance: provider, event/instrument identifier, retrieval timestamp, timezone, license and freshness.
2. Data validation: reject missing scores, stale odds, invalid prices and ambiguous team mappings.
3. Forecast ledger: record predictions before start time, model version, probabilities and immutable evidence.
4. Settlement: compare only against independently verified final results; never use future data in backtests.
5. Metrics: sample size, calibration/Brier score, log loss, coverage and ROI after costs where relevant.
6. Safety: no live orders; read-only market credentials; secret values never logged.
7. Automation: workflow health, failed-job alerts, retries with rate limits and daily Hong Kong time reports.

## Current verification status
Repository structure inspected on 2026-10-16. This document is a checklist and does not certify live API availability, successful workflow runs or model performance.

## Integration contract
Each system should emit a JSON report containing system, generated_at_utc, source_status, forecast_count, settled_count, evaluation_metrics, failures and version. Do not label a system production-ready until end-to-end tests pass.
