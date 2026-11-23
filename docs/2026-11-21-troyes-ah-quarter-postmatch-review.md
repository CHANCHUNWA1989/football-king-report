# 2026-11-21 Troyes - Le Havre research-only post-match correction

**State: HOLD / no model promotion / no betting permission.**

## Observed outcome, not a certified betting record

- Fixture: Troyes 3-1 Le Havre, French Ligue 1, 20 Nov 2026 local France (21 Nov 03:45 Hong Kong).
- Primary club FT report: https://www.estac.fr/estac-3-1-le-havre-les-troyens-renversent-le-hac-au-stade-de-laube/
- Independent score corroboration: https://www.fotmob.com/matches/le-havre-vs-troyes/3axz38
- The conversation mentioned **HOME Troyes -0.25**. Conditional on that *reported* line and FT score, the existing `asian_handicap_research.grade` returns **FULL_WIN**.
- The earlier pre-match conversational assessment was **HOLD**, not an approved positive-EV pick. No authenticated earlier forecast payload, independent timestamp seal, wager execution, or bookmaker price exists for this review. The match cannot be credited to the formal model sample, nor can it be called an actual monetary missed gain.

## Separate direction, EV, gate and ex-post result

| Dimension | Determination |
| --- | --- |
| Lean / directional view | Prior conversation leaned HOME, but this is not a sealed model output |
| Quote & market identity | Reported -0.25, historical reference odds 1.943; no executable quote proof |
| Pre-match value | **UNKNOWN** without independently supported probability distribution, uncertainty and price |
| Gate | **HOLD**, preserved |
| FT conditional settlement | FULL_WIN **if** that line was the market being evaluated |
| True profitability / model uplift | **NOT ESTIMABLE** from this single unsealed outcome |

**Important mathematical correction:** a general binary `p * odds - 1` calculation is not a valid Asian quarter-line EV model without handling half-wins, half-losses and pushes. For a selected team at **-0.25**, with selected-team win probability `W`, draw probability `D` and price `o`:

`EV = W * (o - 1) - D / 2 - (1 - W - D) = o * W + D / 2 - 1`.

At an **illustrative, not authenticated** 1.943 decimal price and *assumed*, not measured, draw probability D=0.285:

- Zero EV threshold for W: `(1 - 0.5 * 0.285)/1.943 ~= 44.13%`.
- +3% theoretical EV threshold for W: `(1.03 - 0.5 * 0.285)/1.943 ~= 45.68%`.
- These are **conditional algebra**, not a verified expected-value edge.

New pure module `ops/asian_threeway_ev_research.py` supports only -0.50 through +0.50 via an exact result-class payoff; larger Asian lines **HOLD** until a full goal-margin distribution is supplied. Claims about odds/quote age/uncertainty are never promoted to authenticated proof. The existing `ops/value_ev_policy.py` remains unchanged for its binary-only cases; do **not** use that binary evaluator to approve Asian quarter-goal selections.

## Source disagreement and lookahead protection

- FotMob publishes match xG **2.64 / 0.63**: https://www.fotmob.com/matches/le-havre-vs-troyes/3axz38
- Maxifoot publishes match xG **1.64 / 0.56**: https://www.maxifoot.fr/match/troyes-havre-20261120.htm
- Both show Troyes creating more opportunities, but differences in provider definition or data collection are not authenticated. Do not average the sources, replace historical input xG with post-match xG or infer pre-match calibration from either.
- Market drift from -0.5 to -0.25 cannot by itself prove a bookmaker narrative or a true downgrade; it is a research flag requiring dated, source-native market history, lineup and injury corroboration.
- The 89th-minute red card and injury-time penalty are **post-kickoff** events, and must never enter a pre-match feature vector.

## Acceptance gates before changing weights or moving off HOLD

1. Freeze exact source-native fixture identifiers, kickoff and pre-kickoff prediction/quote timestamps with immutable hashes; prevent fixture/date aliases or outcomes leaking across the boundary.
2. Confirm **two independently attributable full-time score publishers** and reject contradictions. Score corroboration alone is not cryptographic independence certification.
3. Log the actual Asian line, side and decimal quote at the time of the supposed decision; reject stale/unexecutable or unprovable prices.
4. Require calibrated probability lower bounds and compute **five-grade** payout-aware EV, including exact quarter-line splitting, rather than a binary 1X2 shortcut.
5. Preserve abstentions and winning HOLD cases separately. A successful outcome is neither evidence that pre-match HOLD was a mathematical error nor that EV was positive.
6. Test any role-split, market-drift or xG-source correction on independently sealed **future** cohorts, paired against the unchanged baseline with confidence intervals, per-league coverage and full failure counts.
7. Keep `production_recommendations=DISABLED`, independent proof gates active, draft PR unmerged, and all automated staking disabled.

**Research artifact only:** neither this report nor its regression tests create a betting recommendation, prove ROI, or modify the prospective decision journal.


## Phase 2: binary-EV route audit and research-pipeline fix (2026-11-21)

Code audit on `main` identified that `ops/value_research_pipeline.py::evaluate` previously dispatched to `ops/ev_screen.py::screen_ev` for any named market as long as a caller supplied `odds` and a single scalar `probability`. On an explicitly labelled Asian handicap such as Troyes -0.25, the legacy `p * odds - 1` binary formula can spuriously label a research candidate: it does not account for half-loss on draws. The evidence Boolean fields `calibrated` and `fresh_odds` are caller-supplied and cannot authenticate true execution or calibration.

**Applied to the draft PR only:** explicit Asian market labels (Asian handicap/spreads/AH/handicap/hdp) route to `ops/asian_threeway_ev_research.assess`. Their outputs carry exact *conditional* three-way quarter-line mathematical EV and traceable refusal reasons, but always return `research_candidate=false`. Their nested `research_value_screen_pass` may be true on hypothetical input; it is explicitly **not** a certified value recommendation. No independent actual quote/model proof exists.

- For `-0.25` and `+0.25`, only a valid 1X2 vector can yield a hypothetical margin-class payoff; deeper lines require a **full goal margin** distribution and remain HOLD.
- Missing quote, caller-provided overoptimistic confidence bounds, stale quote claim, malformed side/price and deep spreads remain HOLD.
- The path for historic non-Asian rows is left unchanged for compatibility, but it is *still research-only and caller-attested*, never a production authorization.
- Other potentially fractional markets (e.g. quarter-goal totals) need a separate complete payout-aware routing audit; do not interpret this narrow fix as covering every market or proving all call-sites safe.

Regression: `ops/tests/test_value_research_pipeline.py` now includes spoofed `calibrated=True`/`fresh_odds=True` Asian inputs, aliases, a Troyes -0.25 maths example, unpriceable -0.75 and a non-Asian compatibility control. Existing paper settlement, paired holdout, source/evidence and disabled-production gates remain untouched.

**Deployment gate:** keep this PR DRAFT/unmerged until independent review, full ops regression, CI safety checks, source-native provenance and future out-of-sample audit. Passing unit tests alone does not grant a live betting recommendation.


## Phase 3: exact Asian goal-totals EV (2026-11-21)

Additional correctness gap: pre-existing `ops/value_research_pipeline.evaluate` passed labelled totals such as `over_2_5` through the **binary** `ops/ev_screen.py` function, which ignores pushes and split-stake win/loss outcomes at integer/quarter goal lines. A mathematical example: at over **2.75**, decimal odds **2.00**, P(2 goals)=0.40, P(3 goals)=0.60: the proper exact return is `-0.40 + 0.60 * (2.00-1)/2 = -0.10` units per stake, while the incorrect binary shortcut `0.60*2 - 1 = +0.20` falsely reports a positive number.

**Draft-only fixes:**

- New `ops/total_goals_ev_research.py` uses a complete integer total-goals distribution with exact quarter-line splitting for OVER/UNDER, 0.25 through 15.0. It reports the five settlement grades, theoretical EV, and an optional pessimistic bound using claimed probability lower bounds.
- `ops/value_research_pipeline.py` routes explicit total-market aliases ahead of Asian handicap aliases; conflicting or absent market direction is rejected and both types always have `research_candidate=false`, never a bet or positive-EV certification.
- Regression tests cover 2.25/2.75 half-win and half-loss, whole-goal pushes, 6.75 totals, missing total-goal distribution, spoofed confidence/quote flags, invalid lines, stale prices, aliases and direction conflicts.
- `ops/POSITIVE_EV_POLICY.md` now scopes the simple `p * price - 1` formula to binary full-win/full-loss markets and documents Asian five-grade EV correctly.

**Still outside scope:** source-proven model calibration and immutable forecast cutoff; authenticated bookmaker executable quote; independent FT goal evidence; full audit of all unknown market aliases; statistically powered prospective paired OOS comparison. This is a fail-closed mathematical fix, not proven predictive improvement. **Production remains DISABLED; PR remains DRAFT.**
