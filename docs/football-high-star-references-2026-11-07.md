# High-star football references and research-input integrity

Reviewed on 2026-11-07 UTC using GitHub repository metadata and pinned files.
Stars are a popularity snapshot, not ratings of forecasting accuracy or proof of profit.

| Repository | Stars | Pinned commit | Useful reference and present decision |
| --- | ---: | --- | --- |
| [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) (general ML, not a football predictor) | 68,079 | `6e37063f7ab7ef7a7e257b9d44bc3ec6ee1b1bcd` | Reviewed `calibration_curve`: compare the mean forecast with the observed positive fraction in each bin. Reuse our existing classwise calibration helper; no sklearn/NumPy dependency, calibrator, or upstream code imported. |
| [hudl/open-data](https://github.com/hudl/open-data) (formerly StatsBomb/open-data) | 3,779 | `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb` | README describes competition/season/match IDs and separate events/lineups. Potential future feature research; no datasets imported. These are not executable bookmaker quotes or proof of when our model knew a fact. |
| [probberechts/soccerdata](https://github.com/probberechts/soccerdata) | 2,134 | `b507432742119ba3897533895c92ac3a4f2b9259` | README describes consistent columns/identifiers and local caching. Reuse our current adapters; no scraper installed or invoked. Its own usage notice requires complying with source terms. |
| [ML-KULeuven/socceraction](https://github.com/ML-KULeuven/socceraction) | 824 | `93a1242d46c104889205753accaabadb00c45c6d` | Explicit constrained SPADL schema is a useful research boundary. Adopt the schema-first principle in our existing CSV reader; no SPADL/VAEP model, Pandera dependency, or upstream code copied. README says the project is not actively developed and serves research reproducibility. |
| [PySport/kloppy](https://github.com/PySport/kloppy) | 571 | `a9651eba7c4dbbe2d2fc6d4cffb4aea63fadac11` | README documents a vendor-independent model with explicit event/tracking semantics. Future reference; no provider-ID mappings or source authentication inferred from compatibility. |

## Sources and permissions

- Scikit-learn: checked pinned `sklearn/calibration.py` and `COPYING`; BSD-3-Clause, Copyright 2007-2026 The scikit-learn developers. Only the reliability-diagnostic principle is referenced. Our five fixed bins keep the existing left-closed boundary rule; sklearn's binary function and its boundary/default choices were not transplanted.
- Soccerdata: read pinned `README.rst` and `LICENSE.rst`; Apache-2.0 notice, Copyright 2021 Pieter Robberechts, with an incorporated footballdata notice. API's generic `NOASSERTION` did not establish its licence; the actual file was checked.
- Socceraction: read pinned `README.md`, `socceraction/spadl/schema.py`, and `LICENSE.rst`; MIT, Copyright 2019 KU Leuven Machine Learning Research Group. The schema explicitly constrains column types/ranges and sets `strict=True`. Our local CSV contract still permits uniquely named optional metadata and does not introduce coercion.
- Kloppy: read pinned `README.md`; GitHub metadata identifies BSD-3-Clause. No code copied, so no licence compatibility claim beyond that metadata is needed here.
- StatsBomb: read pinned `README.md`, including its source/logo attribution conditions. No data downloaded; a README and public visibility do not substitute for reviewing applicable data-use terms before integration.
- No third-party program was executed and no provider API, credentials, extra agent, model weights, historical results, or frozen forecasts were used or changed.

## One adopted improvement: unambiguous shadow CSV headers

`model_evidence.read_rows` previously checked required names only after converting them to a set. `csv.DictReader` silently overwrote duplicate columns. A second `market_utc` could hide a post-kickoff timestamp; duplicate probabilities or outcomes could likewise change the scored record without rejection.

Reject duplicate names and empty/whitespace-only names before reading records. Keep existing required-column, time, probability, and duplicate-case checks. BOM, column reordering and uniquely named optional metadata remain supported; input bytes are never rewritten. Existing `publish` and `unified_research` handlers reject the file, remain HOLD/DISABLED and emit no scores for it.

Tests first reproduced eight failures: four duplicate-header cases, two unnamed-header cases, and both consumer entrypoints. The positive optional-metadata/BOM case already passed. After the minimal reader change, 60 targeted tests passed, followed by one complete 2,535-test ops regression with no skips. `compileall` and `git diff --check` passed. Latest commit and Actions results are recorded in Draft PR #451.

This protects research input integrity; it does not authenticate a forecast, bookmaker quote or outcome, establish an out-of-sample advantage, or certify positive EV. Issues #439/#452 remain external blockers. Keep HOLD, production recommendations DISABLED and POSITIVE_EV_VERIFIED=False; no merge or deployment.

## Next adopted improvement: same-case model/market calibration diagnostics

The research center already had five probability bins per home/draw/away outcome, but no per-class ECE or paired market calibration summary. Extend that helper and reuse its existing `score` validation. Invalid probabilities or boolean/out-of-range outcomes are now rejected directly; no records are silently excluded to improve calibration statistics.

For each class, ECE = sum over bins of `abs(sum_probability - positive_count)` / N. Compute this from unrounded statistics, then average the three class ECEs for the macro summary. Each class contains the same N fixtures; the three class views are not 3N independent matches. Empty input has no ECE. Preserve the existing five bin edges, 0/1 handling, empty bins, Brier/log loss/RPS, and frozen inputs.

`metrics` adds `calibration_audit` to existing aggregate and league reports with both model and market curves on the identical fixtures. Positive `market_minus_model_macro_ece` means a lower descriptive ECE for the model; it has no confidence interval and proves neither calibration nor market superiority. Original input timing/results remain unauthenticated by this diagnostic. No weights, predictions, calibration mapping, promotion gate or archived performance reports were changed or regenerated.

Tests first reproduced ten failures across missing diagnostics and unsafe direct calibration inputs. After the change, 71 affected tests passed; one complete 2,540-test ops regression passed without skips, with compileall and diff checks passing. A temporary-file publication test verifies that the existing JSON output carries both aggregate and league calibration without activating recommendations. Latest HEAD/Actions evidence remains in Draft PR #451; HOLD/DISABLED and POSITIVE_EV_VERIFIED=False remain in force.

## Popularity search refresh and licensed normalization reuse (19:41 UTC)

Used GitHub search plus the REST repository-search `sort=stars&order=desc` option for `soccer archived:false`, `football archived:false`, and `football prediction archived:false`. These are query-specific results, not a claim of an exhaustive global ranking. The connector search lacks a sort parameter, so the existing GitHub CLI supplied only that sorted metadata; repository/file reads used the GitHub connector. Stars are a new snapshot and may differ from the earlier table.

| Relevant result | Stars | Assessment / disposition |
| --- | ---: | --- |
| roboflow/sports | 5,483 | README is about video tracking/detection/camera calibration, not pre-match forecasting. MIT metadata; no video, dataset, model weights or GPU dependencies imported. Reviewed README blob `e9863c68c66a03de20489cacbdb360febe6b3afb`. |
| hudl/open-data | 3,788 | Event/lineup data reference already recorded above. Separate data rights and point-in-time availability remain necessary; no dataset downloaded. |
| eddwebster/football_analytics | 2,842 | Repository collection; metadata has no identified licence. No code copied. |
| probberechts/soccerdata | 2,134 | Previously reviewed Apache-2.0 source; reuse existing adapters and avoid extra scrapers. |
| devinpleuler/analytics-handbook | 1,715 | Read README: tutorials, data types and reusable mainstream libraries; MIT metadata. No notebook executed or copied. Reviewed README blob `7e5e56e19b44406df40c6a7addd53d3743255bdd`. |
| openfootmanager/openfootmanager | 1,184 | Manager game, not a forecasting baseline; no game code imported. |
| architv/soccer-cli / manrajgrover/football-cli | 1,132 / 1,084 | Score CLI projects; existing collection/reporting already covers this role. No duplicate collectors introduced. |
| acredjb/FBP / mhaythornthwaite/Football_Prediction_Project / jrbadiabo/Bet-on-Sibyl | 440 / 319 / 288 | Top direct prediction-search results. First/third lack an identified metadata licence; second's metadata says MIT and it was previously reviewed. No models or performance claims imported. |
| martineastwood/penaltyblog | 249 | Lower star count, but a directly relevant MIT football-probability toolkit already licensed in this repo. Reuse its power-normalization algorithm at pinned `6870f0e762e9cba35fa722dc14a8daeaf8bc6134` rather than import an unrelated popular application. |

Integrated a second 1X2 normalization into existing `odds_market`, with the original multiplicative output unchanged. The power method solves a different margin-allocation assumption; agreement/disagreement measures assumption sensitivity, not which method is correct. Both alternatives use the same source event, selections, surviving bookmakers and validated market timestamps. Public output adds only derived consensus probabilities/difference and research flags; no raw prices, bookmaker blocks or keys. Duplicate/stale books retain the original rejection rules. A failed alternative is HOLD/null without filling from the baseline.

Read the complete pinned `_power` function and retained the existing MIT notice/author attribution in `third_party/penaltyblog/`; use bounded Python bisection instead of upstream NumPy/SciPy/Ridder. No dependency installation or vendor request. First tests exposed absent method/report contracts (3 failed assertions and 14 missing-keyword errors); the final 86 relevant tests and one complete 2,546-test ops regression passed, no skips. Hand-derived squared-inverse probabilities, fair/underround/extreme prices, same-book medians, timestamp/price rejection and unchanged fake-collector request counts are covered. Compileall/diff checks passed.

This batch completes one additive research capability; it does not bulk-import the listed applications. Software/data permission, relevance and testability govern adoption. Asian settlement, sealed forecasts, model weights, actual results and historical performance reports remain untouched. Latest HEAD/CI is recorded in Draft #451; HOLD/DISABLED and POSITIVE_EV_VERIFIED=False remain mandatory.

## 2026-11-08: adopted BTTS research capability

The user clarified that the active task is further licensed feature integration, not another administration/provider-status check. Inspected existing goal-market modules and confirmed BTTS was absent. Read the pinned penaltyblog `FootballProbabilityGrid.btts_yes`, `btts_no` and `_sum_mask` implementations in `penaltyblog/models/football_probability_grid.py` (source blob `dbadefed48c5c7835321ecc31cfc175cd85b2a37`, commit `6870f0e762e9cba35fa722dc14a8daeaf8bc6134`). Retain Copyright 2021 Martin Eastwood and the existing full MIT notice in `third_party/penaltyblog/`.

Adapted its positive-home/positive-away score-cell aggregation into the existing `case_goal_market_scoring` grid. No new model, dependency, module, collector or API call. `both_teams_to_score` contains YES/NO probabilities, the candidate observed category, binary Brier `(P(YES)-I(YES))^2`, log loss, and explicit HOLD/DISABLED/unverified flags. It uses original validated goal rates and the current truncation policy; it never estimates goal rates from 1X2 probabilities. Candidate results select the loss term, not the probability distribution.

The existing controlled-case replay and JSON output carry the field with the same input proof references and verifier-call count. Missing goal rates still produce only the legacy four-way replay. The existing 164 AH/totals scenarios remain unchanged; `market_projection_count_basis=AH_TOTALS_FIXED_SCENARIOS` makes that count's scope explicit. BTTS is an additional derived diagnostic, not an offered-market count or a newly sealed forecast.

Tests first reproduced 11 failed missing-feature assertions/subcases. The independent hand calculation with both Poisson rates `log(2)` gives BTTS YES=0.25, NO=0.75 and binary Brier=0.5625 for a YES candidate. Tests cover no-goal/one-team/both-team cases, outcome-independent probabilities, extreme-rate truncation bounds, input immutability and replay integration. Existing identity, time, sealed-rate, invalid-value, quarter-line and no-goal-rate guards remain intact. Final targeted tests: 79 passed. One complete ops regression: 2,549 passed, no skips; compileall and diff checks passed. Exact HEAD/Actions evidence is recorded in Draft #451.

No original proofs, forecasts, weights, results or historical performance reports were rewritten or rescored. No author performance claim or synthetic result is evidence of future accuracy, calibrated BTTS or positive EV. The new field explicitly denies independently verified results, a sealed BTTS forecast, authenticated offered market, calibration and positive EV; HOLD/DISABLED remains in force.

## 2026-11-08: exact-score query and top-five scorelines

Read the same pinned penaltyblog `FootballProbabilityGrid.exact_score` method and confirmed no existing exact-score/top-scoreline output in our research modules. Retained its MIT attribution and adapted its in-grid probability lookup to the existing validated goal-grid reconstruction. Ranking the five largest cells is a local extension, not a claim that upstream provides a top-five API. No new model, module, dependency, provider request or additional verifier invocation.

The existing case replay now carries `correct_score_diagnostic`: five ordered score/probability pairs, their combined retained-grid mass, remaining in-grid mass, and the candidate score's probability/log loss when supported. Exact ties use ascending home/away goals; no sorting by rounded values or outcome-dependent selection. Top-five cells are not renormalized to 100%. The existing 164 AH/totals count and BTTS results are preserved. With rates 2 and 1, the four tied leading cells (1-0, 1-1, 2-0, 2-1) each have probability approximately `2*exp(-3)`; fifth is 3-0. Their combined mass is about 0.4646793, not a validated hit rate.

The 0..24 grid is conditioned on retained mass and the pre-existing tail bounds still apply. Upstream returns zero outside its grid; the local diagnostic instead emits null candidate probability/loss with `OUTSIDE_RETAINED_SCORE_GRID`. It does not mistake truncated support for an impossible actual score. In-grid tiny positive probabilities use their actual finite log loss without an arbitrary probability floor. Negative/invalid scores remain rejected by the existing scoring boundary.

First observed 12 missing-feature assertion/subcase failures. Final targeted tests: 82 passed. One complete ops regression: 2,552 passed, no skips; compileall/diff checks passed. Tests cover hand-calculated probabilities, ties, preserved input bytes/objects, score-independent ranking, complete top/other mass, extreme rates, the 24/25 grid boundary and existing controlled-case replay/legacy no-goal-rate behavior. Latest HEAD/CI is in Draft #451. All new diagnostic trust/market/calibration/positive-EV flags remain False and status HOLD/DISABLED; no original seal, forecast, weights, result or historical performance output was changed or rescored.
