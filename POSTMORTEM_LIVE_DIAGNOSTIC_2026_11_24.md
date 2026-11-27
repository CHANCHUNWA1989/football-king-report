# 2026-11-24 postmortem diagnostic (research only)

Base: e7dde2e9a7eb0a7f2d9c8038e4c570dc7adbecd5. Existing Asian handicap grade and live payout implementations
are independently cross-checked (5,248 grid comparisons). The regression
includes draw/quarter-line, 4–0 away handicap loss, and total-3 push.
The 2–0 at minute 60 scenario is SYNTHETIC, not an archived event from
Brentford–Everton. Card multipliers are sensitivity inputs, not fitted effects.
Do not attribute the entire loss to a card, tune on the postmortem match,
or treat source labels as authenticated evidence.

Paired Brier diagnostics reject duplicate fixtures and declared timestamp
leakage. They do not authenticate archives, establish actual held-out data,
or supply a confidence interval. Existing forward validation remains required.
No provider access, production changes, odds recommendations or promotion.
CI is required; test execution is not claimed by this document.
