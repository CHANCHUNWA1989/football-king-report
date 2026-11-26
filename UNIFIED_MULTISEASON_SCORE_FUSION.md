# Unified multi-season score fusion acceptance

Stacked on #663. Seven pinned OpenFootball cohorts: English Premier League
and Bundesliga 2022/23, 2023/24, 2024/25; Liga MX 2024/25 only.
Total 2398 completed matches. Each league-season starts from empty history;
all forecasts use strictly earlier match dates and at least 50 completed
matches. No match outcomes from assessment seasons select mixture weights.

The five fixed model configurations remain those of #663. Select one of ten
predefined convex weight vectors per EPL/BL using 2022/23 only and the objective
1X2 natural log loss + .25*(binary Brier for U1.5 + U2.5) + .25*(mean five-grade
Asian handicap Brier at home -0.75,-0.25,+0.25,+0.75).
Freeze the selected vector through both assessment seasons. The same score
matrix mixture generates all projections, rather than tuning individual
market probabilities. 2024/25 already inspected; 2023/24 is a temporal holdout
for this implementation but not independently witnessed/unseen.
Liga MX cannot select weights from a separate season; fixed equal weights
are descriptive only.

Paired calendar-week bootstrap (2000 deterministic draws) is exploratory,
unadjusted for multiple comparisons and imperfect serial dependence.
No actual bookmaker lines, quotes, ROI, or EV evaluated. Fixed handicap lines
are research scoring thresholds, not historical offers. No red-card/xG
calibration, provider entitlement, live transport or deployment is established.
Preserve all upstream HOLD/DISABLED gates. Main unchanged.
