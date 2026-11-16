# 2026-11-15 original seven directions: evidence admission ledger

Status: **HOLD / UNVERIFIED**. This document is an audit scaffold, **not a certified result dataset**. The dates are the original research slate in HKT; several European matches may fall on the next HKT calendar day. Preserve original direction and price, not post-hoc re-forecasts.

| # | Fixture (original) | Selection | Reference decimal odds | Quote time/source | Official event ID + FT | Independent second upstream + FT | Kickoff HKT | Lineups / dated absences | Forecast receipt pre-KO | Certified settlement |
|---|---|---|---:|---|---|---|---|---|---|---|
| 1 | Vegalta Sendai v Blaublitz Akita | Sendai -1 | 2.040 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PENDING |
| 2 | Reilac Shiga v FC Osaka | FC Osaka away win (1X2) | 1.910 | UNKNOWN | UNKNOWN (PR #481/#482 note prior LIVE uncertainty) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PENDING |
| 3 | Paris 13 v Red Star | Red Star -1 | 2.020 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PENDING |
| 4 | Finland v San Marino | Under 4.0 goals | 1.934 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PENDING |
| 5 | Eibar v Cadiz | Eibar -0.75 | 1.806 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PENDING |
| 6 | Belgium v Italy | Italy +0.25 | 1.943 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PENDING |
| 7 | Croatia v Czechia | Croatia -1 | 2.010 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | PENDING |

## Admission rules
1. Fixture identity: native event ID, competition, team home/away roles, scheduled/actual kickoff with HKT conversion and source publication/capture times.
2. FT: official native *regulation full-time* status and independent second upstream with documented provider relationship. LIVE/HT/ET/PEN cannot silently count as regulation FT.
3. Source links: include immutable raw snapshots or legally permissible archived references, SHA256, observed time and publisher time. Missing evidence stays UNKNOWN.
4. Team news: official lineup, bench, substitutions, injuries/suspensions with **pre-kickoff** publication timestamps; no hindsight substitution of post-match lineups for known pre-match information.
5. Original model: require independently frozen prediction and version before kickoff; otherwise `FORECAST_NOT_VERIFIED`. Preserve the original seven selections regardless.
6. Settlement: 1X2 away win is **not** an Asian handicap. Quarter handicaps split stake equally across adjacent lines; enumerate full win / half win / push / half loss / full loss. Under 4.0 pushes at exactly four total goals. Settle only certified regulation FT.
7. Prices: these seven decimal numbers have no native bookmaker, market snapshot timestamp, quote execution or license provenance. **Never claim executable return, realized ROI, CLV or positive EV**.
8. Models: compare original A, Poisson, Dixon–Coles on paired chronological genuinely out-of-sample fixtures, same training cutoff, with Brier/log loss and uncertainty. Do not fit to these seven and call it validation.

## Known blockers
- PR #481 and #482 flag J3 coverage absent in the six-league recommender, and historical official LIVE status ambiguity for Shiga/FC Osaka.
- Issues #450/#452 require licensed pre-match quotes, original forecast receipts and independent event evidence.
- No row is admitted to a certified performance denominator yet; `certified_cases=0` **in this ledger**, not a claim about other project datasets.
- `production_recommendations=DISABLED`, `positive_ev_verified=false`.

Related Issue #483; PRs #458, #464, #480, #481, #482.
