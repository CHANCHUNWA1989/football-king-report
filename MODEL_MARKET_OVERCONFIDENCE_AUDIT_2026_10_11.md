# Football King: Market-divergence safety and diagnostic release (2026-10-11)

## Evidence and problem

The existing, unverified seven-fixture forward study shows model 1X2
Log Loss worse than the time-matched market benchmark. The seven results are
too few to calibrate probabilities or infer profitability. Previous
`research_recommender.py` ranked chiefly by top model probability and
top-versus-second margin. If model and market both selected HOME, a difference
of 20+ percentage points was still allowed into the top editorial research
shortlist, and could be described as a 'high probability' case. That promotes
overconfidence despite severe disagreement.

## What has changed (risk policy, not calibration)

The prespecified **12 percentage point** maximum absolute difference between
any model and de-vigged market 1X2 probability component is a conservative
manual-review *heuristic*, not a learned threshold and NOT a claim of
backtested optimality. Its selection here is a research risk policy, not a
fit to the seven outcomes; freeze it prospectively before collecting new
results. A larger difference:
- is downgraded from the eight-item primary editorial shortlist into the
  B verification/review cohort even when the directions are identical;
- is explicitly labeled in JSON, the verification CSV and the iPhone HTML;
- is **not** removed from the full pre-match verification slate or the
  immutable model and market forecasts (both wins and losses remain eligible
  for future settlement);
- does **not** implicitly trust market quotes as executable bookmaker prices
  or certify betting value.

The unchanged 1X2 research predictor and its fixed uniform-shrink A/B
candidate continue in Shadow Mode. No model coefficients are tuned to those
seven matches. Results still cannot automatically promote a betting model.

## New forward diagnostic

`validation.json.measurements.directional_accuracy_audit` tracks model and
market **top-choice hits on identical settled fixtures**, their home-selection
counts and direction agreement. This sits alongside Log Loss and Brier. All
figures remain descriptive, and archived results are explicitly labeled
unauthenticated until independent original-score provenance is established.

## What would make the prediction model actually better

1. Expand the independently settled, frozen pre-match cohort across at least
   12 calendar weeks/four leagues, including unpopular and unsuccessful calls.
2. Compare out-of-sample Log Loss and Brier against the exact earlier market
   consensus; report home/away/draw calibration and direction hit rates
   separately. Monitor probability calibration by bins and rolling weeks.
3. Register candidate model changes **before** future fixtures. Consider
   market-anchored prior, reduced high-confidence extremes, team-strength
   regularization and home-advantage decomposition only as challenger models.
   Do not change production forecasts on the basis of seven settled games.
4. Adopt blocked temporal train/validation/test splits, purged and embargoed
   features, unchanged original timestamps and a shadow-only A/B protocol.
5. Even if a challenger beats the market on a long independent forward test,
   value/ROI still need real legally executable odds, CLV, independent final
   scores and manual approval. `production_recommendations` remains DISABLED.

## Scope and tests

Changed: `ops/research_recommender.py`,
`ops/verification_slate.py`, `ops/model_evidence.py` and their targeted tests.
No new API secrets or calls; no editing of old sealed archives; no promotions
to betting picks; no fabricated match hit rate. Tests explicitly cover
same-direction large disagreements, unchanged archived probabilities,
exported B-review reasons, model-v-market direction counts, and fail-closed
research status.

