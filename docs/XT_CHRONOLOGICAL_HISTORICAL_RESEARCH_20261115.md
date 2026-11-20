# Chronological xT historical research smoke — 12 train / 1 day gap / 4 holdout

**Observed 2026-11-15 UTC. RESEARCH ONLY — NOT PRODUCTION, NOT BETTING.**

This is a **completed, real installed-package research experiment**, not just
a proposed interface. Socceraction 1.5.3 transformed 16 separately
SHA-256-verified StatsBomb 2022 World Cup open-data historical matches
into SPADL, fitted a 6×8 ExpectedThreat surface from **earlier matches
only**, and rated later match actions using that frozen surface.
It does **NOT** establish independent pre-match source capture, actual
out-of-sample predictive accuracy, positive EV, ROI, calibrated Asian
handicap/total probabilities or authorized commercial data usage.

## Original upstream sources and software

- Official [StatsBomb Open Data](https://github.com/hudl/open-data)
  immutable commit: `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`.
  [StatsBomb open research README](https://github.com/hudl/open-data/blob/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/README.md)
  requires StatsBomb attribution and official logo for public research
  writeups. This is **not** a commercial betting or production-data license.
- Competition/season index: `data/matches/43/106.json` at that commit,
  64 indexed World Cup matches, SHA-256
  `b9d7516dc9919a825f04c204ca85487958c8a2431e84140a48e944934661efc7`.
- Exact **16-match split and each of the 32 file SHA-256 digests**, byte
  counts, team IDs, dates and kickoff times live in the tracked
  `ops/research_manifests/statsbomb_wc2022_xt_12train_4eval_20261115.json`.
  Only source metadata/hashes and match IDs were added to GitHub.
  **No proprietary files, raw event JSON, feature matrices, provider keys,
  fitted surfaces or private credentials are committed.**
- Software: [Socceraction 1.5.3](https://github.com/ML-KULeuven/socceraction/tree/v1.5.3)
  uses MIT license
  ([exact v1.5.3 license](https://github.com/ML-KULeuven/socceraction/blob/v1.5.3/LICENSE.rst)).
  Real isolated Python 3.11 package versions:
  `socceraction=1.5.3`, `pandera=0.17.2`,
  `multimethod=1.12`, `pandas=2.3.3`,
  `numpy=1.26.4`. `pip check` passed.
  **These are exact observed research versions, NOT a separately
  hash-locked/audited complete dependency graph.**

## Strict historical timeline

| Dataset | Actual match dates (2022) | Matches | SPADL actions | Model use |
| --- | --- | ---: | ---: | --- |
| Earlier training group | November 20–23 | **12** | **25,752** | `ExpectedThreat.fit(train)` |
| Explicit embargo | November 24 | **0** | **0** | Neither trained nor rated |
| Later held-out group | November 25 | **4** | **7,967** | `ExpectedThreat.rate(holdout)` **only** |

Training IDs:
`3857286, 3857271, 3857285, 3857282, 3857300, 3857254,
3857265, 3857279, 3857277, 3857284, 3857291, 3857268`.

Held-out IDs: `3857273, 3857301, 3857274, 3857272`.

All match IDs are distinct and source-hash checked against the **same
immutable official data commit**. This **chronological historical split**
does not constitute *prospective* out-of-sample certification because
source records were obtained long after those matches, the test design
was selected retrospectively, and independent publication/capture-time
attestations are absent. No pre-match bookmaker prices were accessed.

## Actually executed, independently repeatable technical checks

A fresh temporary Linux Python 3.11 research environment successfully:
1. Fetched the upstream competition index from the fixed Git commit and
   validated its SHA-256; selected the exact 12 + embargo + 4 sample.
2. Downloaded and SHA-256-checked **all 32 official event/lineup JSON**
   files (48,689,446 total bytes), in an isolated workspace only.
3. Converted every sample with the supported **local StatsBombLoader →
   Socceraction SPADL converter**. Verified native game IDs, both teams,
   action IDs, action clocks, standardized 105×68 metre coordinates.
4. Fitted `ExpectedThreat(l=8, w=6, eps=1e-5)` using **only the 12
   train DataFrames**, and used `rate(..., use_interpolation=False)`
   **only on four later matches**. The research xT 6×8 surface was
   finite and bounded, fitted in 50 iterations, with SHA-256 of its
   raw `numpy` bytes:
   `0bca9abf1baf9ecc7d903e7026710db1ec73ed804fe856e9aee570aceef078dd`.
5. Observed **6,084 xT-rated actions** in the 7,967 later SPADL
   actions; unrated actions were expected NaN because Socceraction
   only rates successful ball-progressing action types. This coverage
   is **not** predictive performance or a verified edge.
6. Downloaded the *actual GitHub files* at PR commit
   `0c333098b5afa0da973c7ad54d1cabaaa63cedc5`,
   checked every file against its connected-GitHub Git-blob SHA, then
   reran the checked-in entrypoint:
   `status=RESEARCH_ONLY`, training **25,752**, holdout **7,967**,
   rated **6,084**, identical xT SHA.
   The same run executed **18 synthetic security tests (OK)**.

**Real negative preflight tests** against this already downloaded local
historical sample:
- Changed one event JSON byte **without changing length**: CLI exited 1
  with `HISTORICAL_SOURCE_SHA256_MISMATCH`, before optional model imports.
- Changed a held-out match date to a date before the embargo: CLI exited
  1 with `CHRONOLOGICAL_LEAKAGE`, before any model fitting.

## Safe research entrypoint — no network fetch, no real data in GitHub

```sh
# ONLY after independent source-license review and local, vetted package
# installation; prepare the 32 exact files from the immutable official
# commit in directories events/ and lineups/ under /private/wc2022.
python -m ops.xt_chronological_research \
  --manifest ops/research_manifests/statsbomb_wc2022_xt_12train_4eval_20261115.json \
  --data-root /private/wc2022
```

The program verifies the full manifest and **all 32 local file lengths
and hashes first**, before any optional Socceraction/pandas/numpy import.
It copies already verified bytes into auto-deleted temporary source
directories for StatsBombLoader; **never downloads, scrapes or writes
trained output files**. It rejects wrong upstream commit, ID overlap,
embargo violations, missing/altered files, wrong package versions,
cross-match teams, invalid action clocks and coordinates. Report includes
only aggregated counts and the xT surface checksum.

The **default GitHub Actions CI** does not install Socceraction, download
provider data or fit xT. It runs only the **18 synthetic stdlib gate tests**.
The real-history model run took place separately on an isolated external
research runner. Do not claim the default CI itself performed that fit.

## Blockers before any further use

- StatsBomb public research availability does **not** prove licensed rights
  to use event feeds commercially for a betting product, distribute
  protected source files or train production models. Independent data
  use approval is required.
- Historical chronology does not independently prove feature availability
  **before kickoff**. Source capture/availability, match outcomes and
  executable odds must be sealed and corroborated prospectively.
- 12 train matches are insufficient for robust xT calibration claims;
  no independent statistical significance, comparison baseline,
  rolling-origin evaluation or uncertainty bounds exist yet.
  This trial did **not** evaluate whether xT improves 1X2, AH or totals.
- Separate Socceraction direct `Kloppy→SPADL` conversion remains
  incompatible at these versions; this run uses the supported
  **StatsBomb→SPADL** route.
- `main` remains unprotected, zero independent PR approvals, and
  [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439)
  remains unresolved.

**PR #470 stays OPEN/DRAFT/UNMERGED; HOLD and
`production_recommendations=DISABLED`. No certified prospective samples,
no independently verified positive EV, no model deployment.**
