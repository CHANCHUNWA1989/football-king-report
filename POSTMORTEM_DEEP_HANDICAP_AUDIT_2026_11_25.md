# Deep handicap evidence and strong-side calibration audit (2026-11-25 HKT)

Research only; HOLD / DISABLED. No model fitted or promoted.

## Exact source and observed coverage
Read evidence/settled.json from commit 5183188ce456ba3422beee4ce5e670fc0a5ca026,
blob f546c96def382659ee9d74d6ef40e823a223e4a9, all 105 rows.
All have p, m, y, league, kickoff/forecast/market timestamp metadata; 0
independently verified results. No row contains a full-time score, goal-rate
pair, score PMF, actual Asian line or executable price. 39 have event ID,
10 have source fixture identity. League sizes Bundesliga 46, EPL 13,
Serie A 9, La Liga 11, Ligue 1 7, Championship 19.
No eligible paired deep Asian handicap evaluation; 0/105, certified 0/300.

## Actual exploratory 1X2 strong-side audit
Computed directly from the archive, selecting side i=0 when p[0]>=p[2],
otherwise i=2, using the archived outcome y. On the SAME selected sides
compare p[i] and derived market consensus m[i]. Binary Brier mean (p[i]-
indicator(y==i))^2, not multiclass Brier. Thresholds 0.60 and 0.75 are
descriptive choices made for this audit, not preregistered fitting thresholds.

| Model probability range | n | Wins | Mean model p | Mean market p | Binary Brier model | Binary Brier market |
|---|---:|---:|---:|---:|---:|---:|
| >=0.60 | 27 | 15 | .689130 | .600317 | .261617 | .225403 |
| >=0.60 and <0.75 | 22 | 12 | .662187 | .580842 | .259918 | .214841 |
| >=0.75 | 5 | 3 | .807681 | .686008 | .269090 | .271873 |

The first group observed 15/27=55.56%, versus model 68.91%: descriptive
overprediction 13.36 percentage points. Market 60.03%; difference 4.48 pp.
The 5-row subgroup is very small, all Bundesliga. No significance or
independent calibration claim, no deep-line inference, no verified ROI.
Archive has been inspected before; this is not an untouched test cohort.

## Non-identifiability example, synthetic only
Two score PMFs with identical 1X2 (0.70,0.20,0.10):
A: P(1-0)=.70, P(0-0)=.20, P(0-1)=.10.
B: P(3-0)=.70, P(0-0)=.20, P(0-1)=.10.
Home -1.25: A has .70 half loss and .30 full loss, B .70 full win
and .30 full loss. Home -1.75 and -2: A all full loss, B .70 full win
and .30 full loss. Identical 1X2 does NOT imply deep handicap calibration.

## Existing implementation and next gates
PR #511 exact head 496bf2fc7eae8c7bda9662d59c76d33b77c819e8
already implements a common grid for rho=0 and fixed rho=-.05; its
asian_handicap function accepts quarter-lines through the existing grader.
PR #490 exact head 24e95a63b1f54cfa64b2ccd34705183aa6d2c816 has a dynamic
Poisson challenger; its historical evaluation is already inspected and
date-only, not an independent forward cohort.
Do not fit a shrinkage coefficient from the above 27 outcomes or assume
market consensus is ground truth. Pre-register identical fixture and
forecast cutoff, as-of input data, all model PMFs and versions, actual
bookmaker market kind/line/quote time (separate Asian vs HKJC three-way),
regulation-time full score with independent authorized sources, and
sealed raw provenance. Compare full five-grade categorical Brier and
log loss, calibration and paired kickoff-week cluster intervals on
untouched fixtures, reporting cohort attrition and sample size by line.
Minimum 300 certified prospective records is an existing overall release
gate, not proof of sufficiency for individual deep-line strata. No
production or main modifications.

## Previous regression exact-head verification
Commit 5183188ce456ba3422beee4ce5e670fc0a5ca026: all 5 PR workflows success.
Security regression run 45513566419 job 138867143665 raw logs explicitly
show all three new test methods ok (9+7+16384 scenario comparisons).
Ran 2366 ops tests and 117 legacy tests. These are software tests, not
football prediction evidence. This documentation commit requires its
own exact-head CI. No new executable change in this commit.
