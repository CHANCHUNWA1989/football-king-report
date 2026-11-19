# Football-King | Real future four-model pre-match research gate

**2026-11-16 HKT. Draft PR #487 (stacked over Draft PR #458). Research only.**
**HOLD / production recommendations DISABLED / positive EV false / 0 certified samples.**

## Why

The historical 2025-train / 2026-186-test evaluation and 2,000-draw date-cluster
uncertainty experiments both reuse an already inspected cohort; they CANNOT
legitimately approve model selection. The next evidentiary step is to capture
all models on genuine FUTURE games before kickoff, strictly using one
real-world source response and a common pre-match cutoff.

## What is implemented

1. `ops/live_bundesliga_three_model_probe.py --with-bivariate` retains the
   **unmodified original A** `predict_league` algorithm and live OpenLigaDB
   one-GET source, invokes existing actual installed Poisson/Dixon-Coles
   three-model same-cutoff capture, then fits optional Penaltyblog
   `BivariatePoissonGoalModel` (equal weight and the fixed unoptimised
   xi=0.003/day variant) before the SAME cutoff. No future results used.
2. `ops/bivariate_four_model_prematch_gate.py` rejects retrospective,
   expired or ambiguous local time, incomplete A/Poisson/DC vectors,
   inconsistent native team IDs/league/fixture, failure of *either* fourth
   model variant, and incomplete same-response training history.
3. Original A draws on ALL valid finished fixtures in the one-GET response;
   challenger rows also need source-native IDs. To avoid fake
   same-batch claims, the live runner compares A's entire prior-match
   event-ID set with the native-ID challenger event-ID set **exactly**.
   If any eligible A row lacks native identity, four-model completion is
   **BLOCKED**, even if three-model research vectors were produced.
4. A capture is only locally pre-match: source publisher rights/authenticity,
   first-known result times, independent official fixture identity and a
   trusted third-party TSA/Rekor witness are NOT proven. The record's
   `source_response_sha256_unattested` and GitHub CI/log timestamps are
   audit aids, **not** official source or external time authority proof.
5. The fourth model returns 1X2 plus **hypothetical** Over-2.75 and
   home AH -0.25 five-grade settlement probability masses, not
   sportsbook quotes, positive EV or actual betting recommendations.
   Production remains disabled even if all four models fit correctly.
6. A new **read-only GitHub Actions** workflow
   `.github/workflows/bivariate-bundesliga-prospective.yml` checks
   `packages/football_king_v4_1_iphone_verified.zip` by fixed SHA256,
   installs real upstream Penaltyblog v1.13.1, performs a single
   OpenLigaDB GET in the same process, and (ONLY on success) uploads a
   14-day research artifact of the future four-model local capture.
   If it is too late, fixture identities drift, historical source rows
   are missing, or no real future match exists, the job **fails closed**
   and does NOT emit a successful pre-match forecast.
7. Independent unit tests cover identity, timing, forced failure,
   history-completeness, immutable inputs, and inability to treat prior
   scores or post-cutoff predictions as genuine prospective captures.

## Read and interpret the result

A workflow passing means a *technical genuine pre-kickoff research
capture* has been produced using a current third-party source. It **DOES
NOT mean** independently certified match/score/odds evidence, calibrated
model improvement, verified EV or a tradable recommendation.

This is not a continuous service: `pull_request` on relevant files and
explicit workflow dispatch only, **not** a recurring future-match scheduler.
Every run is bounded by actual time and current verified gateway input.

**Next gating steps**: persist unchanged early forecast artifact digest and
GitHub run/head ID, obtain trusted external timestamp and independently
verified fixture/score availability, let match finish, collect official and
second independent FT sources, then paired forward log loss/Brier with
no post-hoc model tuning. Bookmaker quotes and tradable Asian lines remain
separate from research simulation.

No scheduled betting, repository main merge, auto model selection, or
wagering is performed.
