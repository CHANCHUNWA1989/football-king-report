# Multi-Source Core (historical research first)

Run from repository root: python ops/live_core_multi_source.py --open-public
Optional authorized local fallback: --local-mex-csv /private/MEX.csv

OpenFootball: https://github.com/openfootball/football.json/blob/master/2024-25/mx.1.json
Git blob 01eb9b765c10372ad3dd5ebe8a2067bfc4376223 was read through GitHub
and contained 340 finished Liga MX 2024/25 fixtures. Public-domain project.
The 2025-26/mx.1.json path returned 404 at inspection; do not assume coverage.
CI reads the fixed public URL once and verifies the original Git blob; if
upstream changes, fail closed, never silently update the pinned cohort.
Football-Data: https://football-data.co.uk/mexico.php (local CSV only; operator
must confirm allowed use). No real CSV validated in this revision.
StatsBomb: historical event/xG candidate only; no Liga MX in the inspected
competition list; follow its agreement and attribution. StrikerAPI is a
historical/prematch candidate only, no installed connector or credentials.
API-Football and Sportmonks live capture paths remain unchanged and gated.
Public web is manual corroboration, not authorized automated scraping.

The baseline uses previous match dates only and a 50-match minimum history,
league-level Poisson, no fitted team model or price. It is retrospective,
not a genuinely frozen forward forecast. No source authentication, EV,
live substitution, calibration claim or automatic promotion.
The additional public-read CI is secret-free and outputs aggregate results.
No third-party raw dataset committed. HOLD/DISABLED.
