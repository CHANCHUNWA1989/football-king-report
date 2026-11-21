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
