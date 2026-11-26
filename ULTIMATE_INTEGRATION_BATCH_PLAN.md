# Ultimate integration — batched delivery plan
Date: 2026-11-26 (UTC+08). Baseline: PR #666 exact head 8106685dae68a26fdf22265fe0f8eb9fe61ecefc, seven successful workflows, 102 offline tests, 545 paired historical evaluations. Not a production release.

## Delivery rules
Use one isolated research branch and one draft PR per coherent batch; stage code, tests and acceptance documentation before opening the PR. Run comprehensive CI against the final head, record job links and artifacts, repair genuine failures, never bypass checks. Preserve frozen baselines, don't repeatedly retune on holdouts. No fabricated source credentials, prices, forecasts or sample credit; no provider purchases or main changes. A passing CI is engineering evidence only. HOLD and DISABLED remain unconditional pending independent review and release authorization.

| Batch | Scope | Exit evidence |
|---|---|---|
| A | Data quality, score encoding sensitivity, chronological historical evaluation, regression | Both frozen pins and cohort counts preserved; conditional inclusive scenario reported separately; test logs; independent confirmation of 39 results still required |
| B | Authorized two-source ingestion, synchronized scores/cards/xG/quotes, durable immutable capture | Independent publisher provenance, valid authorization, timestamps and clock agreement, fixture mapping, stale/revision quarantine, replay and failure recovery with real captures |
| C | Dynamic score distribution, red cards, keeper PSxG, tactical and stoppage effects | Representative labeled data, temporal training/calibration splits, event timing, paired out-of-sample scores and uncertainty; no missing fields inferred |
| D | Independent prospective verification and model selection | Frozen preregistered model, independent timestamped forecasts and settlement, prespecified sample/power and clustered intervals, no leakage; per-market calibration gates |
| E | Market settlement and risk validation | Actual timestamped executable quotes, exact Asian settlement, fees/voids and uncertainty; net return evidence and adverse scenarios; independent release decision |

A is executable now with public pinned data; B–E can prepare interfaces but cannot earn acceptance without their actual dependencies. Provider entitlements, genuine live odds, PSxG and prospective observations are missing. Do not manufacture sample counts. Every batch ends with a short evidence ledger: exact head, workflow results, measured model changes, unresolved dependencies and decision. Do not confuse conditional 0-0 interpretation with actual result verification.

## Batch A analysis contract
Preserve original explicit-ft-only cohort (EPL 353 of 380; BL 294 of 306). Add a separate conditional scenario assuming every alternate [0,0] record is a genuine scoreless draw. Keep original frozen candidates (team/Elo), fixed dates and prior-date-only state updates. No retuning or production selection. Report both cohorts' sample counts and market metrics, not a bound on all possible missingness patterns. Independent result confirmation remains necessary.
