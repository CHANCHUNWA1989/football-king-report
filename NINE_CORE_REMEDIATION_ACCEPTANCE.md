# Nine-core remediation acceptance matrix

Base #665 head 1dc0809fc454413a1f10e9c40eb816248ec9c6ad.
Audited exact-head stacked lineage #657 through #665: all nine PRs remain
draft/unmerged, 58/58 workflow runs successful (6+6+6+6+7+7+7+7+6).
#665 specialist job 139693500587: 83 tests passed. #664 fusion job
139692012779: seven tests and actual pinned historical comparison.

| Requirement | Delivered | Still blocked |
|---|---|---|
| Synchronized multi-source data | multi-cut original-byte replay and strict mapping, clock, state checks | authorized real captures, independent publishers and clock attestation |
| Red-card dynamics | nine explicit sensitivity scenarios; historical event parser inherited | fitted causal/predictive coefficients, sufficient representative red-card data |
| xG revisions | quarantine decreases, disappearance, changed clocks and replayed pairs | genuine immutable source sequence and authorized correction resolution |
| Keeper model | same-cut PSxG/conceded diagnostic schema; missing stays missing | actual PSxG and out-of-sample incremental value |
| Knockout context | explicit format, aggregate and tie-rule claims | independently verified tournament rules and fitted effects |
| Stoppage | 0/5/10-minute sensitivity before 90, optional announced-time diagnostic | trained duration distribution and supported live stoppage clock |
| Independent model evaluation | new later 2025/26 historical subset with frozen #664 choices | missingness bias, genuinely witnessed forward forecasts |
| Market EV/risk | existing quote checks integrated; model_edge null, no certification | authorized executable quotes, actual settlement and calibrated uncertainty |
| Integration/stress | private multi-cut CLI, 14 new test methods, dedicated read-only CI | real provider E2E, independent review and release approval |

Historical data from OpenFootball public-domain source:
https://github.com/openfootball/football.json/tree/master/2025-26
EPL 353/380 and Bundesliga 294/306 rows have explicit score.ft values.
The other 27 EPL and 12 BL rows contain score=[0,0] rather than an ft object.
They are excluded from the original frozen FT-only cohort, not proven missing
results. Some or all may represent genuine scoreless draws; this exclusion can
bias low-score, draw and totals assessment. Do not promote based on this cohort.
Both Git blob pins were verified; the parser rejects any other score encoding,
fixture duplication (including excluded rows), out-of-season dates and count drift.
Five regression tests exercise these contracts. A separately predeclared inclusive
cohort with independent result confirmation is needed to assess selection bias.
Frozen choices team and Elo respectively, no reselection. 302/243 common
assessment matches after >=50 prior-date results. In-chat independent
calculation using the #664 fixed algorithm: EPL log loss 1.06325108 ->
1.02554430, AH Brier .59418376 -> .56957125, U2.5 Brier .24322925 ->
.25289817 (worse). BL log loss 1.06307275 -> 1.01360799, AH Brier .59217090
-> .55884546, U2.5 Brier .22289509 -> .22242359. Composite improvement
weekly paired bootstrap intervals [.01175,.06878] and [.03657,.07872].
Exploratory, unadjusted, not prospective; alternate-encoding exclusion may bias results.
New CI repeats fixed cohorts without credentials. No market prices inferred.

StatsBomb Open Data (https://github.com/hudl/open-data): four additional
original event files inspected from first four 2022 World Cup matches
ordered by match date/native ID. No usable post-shot xG field identified in
those files. No raw event files or derived event statistics published here.
Research remains subject to provider terms/attribution.

Private runner: python ops/live_core_nine_remediation_cli.py /private/history
Manifest schema nine-core-private-history-v1; see tests for fabricated example.
2-48 cuts, fixed ordered filenames NN-api-football.json and
NN-sportmonks.json, captured-byte SHA-256, no secrets or external I/O.
Hash chain is a caller-supplied replay, not durable complete-history proof.
No auto-resume, no historical forecast rewrite, no actual authenticated source,
no fitted keeper/tactical/stoppage/red coefficients, no EV or forward credit.
Main unchanged. HOLD/DISABLED is unconditional.
