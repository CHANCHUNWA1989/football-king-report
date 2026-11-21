# 2026-11-16 — Real 186-game same-cohort 1X2 / Asian handicap / totals OOS

**PR #458 research only. Never automatic betting or promotion.**

## What changed

The existing repository already has independent, tested quarter-handicap and quarter-total settlement math:
- `ops/asian_handicap_research.py`: exact HOME/AWAY handicap quarter-line split, score grading and independent Poisson 5-grade distribution.
- `ops/all_market_scenarios.py`: quarter-goal over/under 5-grade distribution and fair-price algebra (not a bookmaker quote).

New `ops/real_2026_three_market_oos.py` reuses *both original modules* rather than creating a rival settlement algorithm. The existing original A role-shrinkage 1X2 function now exposes **the same home/away expected goal rates** through `_original_a_real_rates`, preserving the original 1X2 function outcome; the new evaluator independently asserts the rate-derived 1X2 vector is *identical* to the existing A formula for each test fixture.

### Exactly separated real results

Pinned `martj42/international_results` Git original CSV, checked against its Git blob:
- **Train**: 260 European-country internationals with real 2025-01-01 through 2025-12-31 full-time scores.
- **Held out**: all 186 eligible different games from 2026-01-01 through 2026-10-06; **zero** 2026 outcomes passed as model training inputs. All three markets are evaluated over the same 186 fixtures.
- No historical original publication/kickoff times, native UEFA team identifiers, neutral-site adjustment, independently signed predictions or bookmaker offered lines/odds are in that CSV. This is a *retrospective date-split test*, **not** independently attested forward betting proof.

Each game obtains A's rates from **2025 ONLY**, then the preexisting goal distribution code predicts fixed, predeclared **hypothetical** handicap and totals grade distributions:

- 1X2: original A, HOME/DRAW/AWAY 3-class;
- Asian handicap: HOME -0.25, AWAY +0.25, HOME -0.75, AWAY +0.75;
- Total goals: OVER 2.5 / UNDER 2.5, OVER 2.75 / UNDER 2.75.

Each actual held-out FT score is graded with exact half-win, push, half-loss rules, then paired **multiclass Brier** and **negative log likelihood** are scored separately *against that market's same-class training-only 2025 historical frequency baseline*, with Jeffreys smoothing to prevent zero-probability categories. **Do not compare absolute 3-class and 5-class Brier as if identical scales** or select the profitable line after seeing 2026 outcomes. The fixed line/side menu is illustrative, not a claim any bookmaker offered these prices.

This provides actual held-out **market-grade probability quality evidence**, NOT verification of any real EV or return on investment. True profit/ROI requires independent authenticated/as-of market odds, exact offered lines and selection frozen before kickoff, source rights, model calibration and external FT verification.

### New real Bundesliga research output

`ops/live_bundesliga_three_model_probe.py` now includes original A’s actual expected goals from the same OpenLigaDB GET, plus six hypothetical AH and OU scenario distributions using the *same existing* settlement modules. It also retains the three fitted model 1X2 vectors (A/Poisson/Dixon–Coles). **Poisson/DC are currently 1X2-only for this handoff**. The new AH and totals scenarios use original A rates; do not claim three independent goal-market models were calibrated or show offered odds not collected. The two presently targeted Nov 21 Bundesliga games are still unverified prospective forecasts.

### Acceptance

Research CI:
1. Check `test_real_2026_three_market_oos.py` edge cases against existing settlement logic and no wager claims;
2. Run `real-2026-three-market-heldout` against **actual pinned public 186 scores** and require exactly 260 train / 186 held-out and nine fixed predeclared market targets (one 1X2, 4 AH, 4 totals);
3. Re-run pre-existing original A/Poisson/DC historical and safety suite without changed 1X2 fit;
4. Validate `status=HOLD`, `positive_ev_verified=false`, `historical_market_roi_or_ev_verified=false`, `production_recommendations=DISABLED` regardless of model outcome.

**Next engineering dependency:** add genuine time-stamped AH and totals bookmaker quotes, verify both sides and captured/original kickoff timestamps (with independent fixture identity), and build separately calibrated real 2026+ forward-market outcome probabilities; only then assess EV or user-stated odds >=1.80. Preserve Draft PR #458 and main Issue #439 review protections. No signing, merging, betting or model promotion in research CI.
