# PR #458 — 2026-11-16 forward-only three-model veto + actual Over-2.75 results audit

**Research-only, not production.** Original A (adapted national-team algorithm), actual installed Poisson and Dixon–Coles evidence already on PR #458. Their frozen 2026-11-15 8-match forecast belongs to [GitHub Action #43711801983](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/43711801983) and [immutable PR comment #6894036843](https://github.com/CHANCHUNWA1989/football-king-report/pull/458#issuecomment-6894036843).

## Why this change is necessary

Actual 2026-11-15/16 results: the 8-model paired cohort had original A 6/8 correct, Poisson 4/8, Dixon–Coles 4/8; real [postmatch settlement comment #6907192871](https://github.com/CHANCHUNWA1989/football-king-report/pull/458#issuecomment-6907192871). On Belarus–Albania (0–2) and Spain–England (2–3), A's preferred away result disagreed with challengers, and the A result won. The source history in the 20:03 HKT live run stopped **2026-10-06** — 40 calendar days before the 2026-11-15 live observation. **That cohort cannot be "fixed" by applying new filters after results.** It only motivates the restrictions in a future, untouched group.

### New future-only read-only screening contract

`ops/forward_three_model_recommendation_screen.py` consumes only the expected, pre-existing, *unverified* original-A adapted + Poisson + DC 1X2 live runner output:

1. Source schema/publisher/unverified time/result claims must match the original fail-closed observation exactly. Incoming output asserting externally authenticated, positive EV, eligible production, or certified prospective samples is REJECTED rather than silently accepted by a weaker filter.
2. **True unobserved kickoff at screening time**, source capture and all three model computations strictly before kickoff minus **10 minutes**. Missing, future or backwards source and model clocks FAIL.
3. Most recent score in the source cannot be over **14 calendar days old at original source observation**. This is a *conservative pre-registered research cut-off*, not optimized against results. A 14-day-old league-wide most recent score is STILL NOT proof both teams' recent results are complete; must separately authenticate team-level latest fixtures for production.
4. Exact one winner in each of three models, all agreeing on **HOME / DRAW / AWAY**; otherwise `MODEL_TOP_DIRECTION_CONFLICT_OR_TIE` and reject. Even if all agree, a **greater than 20 percentage point** spread between their confidence on that direction rejects as `TOP_PROBABILITY_SPREAD_ABOVE_20PP`.
5. No future clock rewinding, duplicate match identifiers, contradictory source team identities, nonfinite probability, invalid sum or missing model. Fails closed.
6. A fixture passing these gates is only `UNVERIFIED_RESEARCH_CANDIDATE`. Even so, the **entire report is always HOLD / DISABLED / zero EV**; *never* a recommendation, signed audit, proven over/under model or permission to trade.

`ops/tests/test_forward_three_model_recommendation_screen.py` checks this behavior with adversarial inputs and a **frozen real original Belarus snapshot (not a new outcome)**. The Belarus real snapshot must show **both** stale-history and three-model-disagreement vetoes. Those reasons are diagnostic; they do NOT retroactively raise the Nov15 8-match win rate.

The old `real-unl-tonight` CI job is **removed** as of November 16: it was a one-night, truly prospective capture and would now rerun concluded games as a fake new prematch test. Keep the original immutable CI run and PR comments; future fixtures require a new explicitly verified match schedule and a new truly pre-kickoff capture.

### Actual goal-market (Over 2.75) retrospective result audit

`ops/real_2026_goals_275_audit.py` independently re-reads the already-pinned actual public `martj42/international_results` Git blob and computes Over-2.75 exact settlement from genuine finished UEFA-national-team matches. It does **NOT** model total-goal scoring, fetch odds, or claim EV.

- **2025 260 actual national-team results**: 0–2 goals 106, exactly 3 goals 44, 4+ goals 110.
- **2026 separate-year 186 actual national-team results** (through Oct 6): 0–2 goals **92**, exactly 3 goals **50**, 4+ goals **44**.
- Over 2.75 at a **purely illustrative constant decimal 1.78** pays -1 unit when <=2, +(1.78-1)/2 = +0.39 when exactly 3 (half-win), and +(1.78-1)=+0.78 when >=4. Thus unconditional/flat-stake **ILLUSTRATIVE** returns are 2025 -1.17%, 2026 -20.53%; the actual 2026 distribution's sample price-to-breakeven is **about 2.333**. These are all *thought experiments*, **not a reconstructed market ROI**. Real historical executable odds and line timestamps were not present; no time-aligned selection existed.
- Do not merge this outcome-only analysis with the earlier 186-match **1X2** date-split hit-rate as though an O/U predictor was tested. An O/U predictive model would need forecasts pinned BEFORE kickoff, exact line and historical feasible odds, and prospective/paired scoring.

CI adds a genuine online HTTP pull of the pinned public CSV (immutable blob identity verified by source reader) and asserts 186 actual results/counts. This confirms real score decoding and correct Asian-goal settlement; **it cannot certify any historical quote or profit**. Synthetic unit tests guard quarter-line half-win, wrong score and illustrative-price claims.

## Next genuine prospective experiment

**Only AFTER** a current source is proved present, use authenticated fixtures, independently observed recent results (including both teams), current roster/news availability, and observed executable/as-of odds from a permissible provider. Freeze A/Poisson/DC forecasts, goal-line probabilities and exact market line before kickoff; then score after official independently crosschecked FT. Never re-select after score publication or hide losses. Preserve HOLD/DISABLED and do not merge/enable a signer without protected-main controls and independent approval [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439).
