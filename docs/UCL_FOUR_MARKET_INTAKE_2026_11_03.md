# UEFA Champions League four-market shadow intake — 2026-11-03

## Scope and factual anchor

**2026/27 Champions League matchday 4, 3 November 2026, 21:00 CET = 20:00 UTC
= 4 November 04:00 Hong Kong.** UEFA's public fixture list confirms the four
home/away pairings: Atlético de Madrid–Bayern München; Feyenoord–Inter;
Barcelona–Aston Villa; Villarreal–Paris Saint-Germain.

Official schedule reference:
https://www.uefa.com/uefachampionsleague/news/02a8-2174c9e9019d-f909a77bd77a-1000--2026-27-champions-league-all-the-phase-fixtures/

**Internal case IDs are not UEFA native fixture IDs.** User-supplied lines are
request metadata, not evidence that a bookmaker offered that line or price.

| Internal case | Market (requested) | Result grading |
| --- | --- | --- |
| ucl26m4-atletico-bayern | Atlético +0.25 | home handicap |
| ucl26m4-feyenoord-inter | over 9 full-time corners | full-time corner total |
| ucl26m4-barcelona-villa | over 1.75 first-half goals | first-half goal total |
| ucl26m4-villarreal-psg | Paris Saint-Germain -0.75 | away handicap |

## Actual implementation

- `ops/ucl_four_market_shadow.py` is **isolated research-only intake**; it
  makes no network calls, uses no API keys, does not modify the published site
  or training datasets, and does not enable any production recommendation.
- Reuses the existing `asian_ev_research.asian_net` quarter-line settlement
  arithmetic and `asian_ev_quote_gate.assess_quote` chronology gate;
  deliberately avoids duplicating an odds scraper or a second EV model.
- All four requested lines have five-grade settlement behavior:
  full win / half win / push / half loss / full loss. For example,
  9 full-time corners **push** on over 9; two half-time goals **half win**
  on over 1.75; Atlético draw **half win** at +0.25; PSG wins by one
  **half win** at -0.75.
- Optional discrete distributions are supplied **by the caller** and are
  explicitly **unverified assumptions**. The code does **not** invent a
  model, parameter estimates, fair odds, edge, success rate or EV.
- Optional bookmaker quote claims undergo fixture/market/line and UTC
  chronology tests with a **120-second capture and update age ceiling**.
  Passing these tests merely establishes structural recency. It does
  **not** authenticate the publisher, existence, availability, licence,
  market execution, bookmaker independence or native fixture identity.
- Public report contains no raw price, private bookmaker ID, API key, or
  detailed third-party quote payload.
- Even if all inputs pass their *structural* tests, global and per-case
  status remain `HOLD`, `bets_authorized = 0`, and
  `production_recommendations = DISABLED`.

## Offline reproduction

```bash
python -m compileall -q ops
python -m unittest discover -s ops/tests -p 'test_ucl_four_market_shadow.py' -v
python -m unittest discover -s ops/tests -q
python ops/ucl_four_market_shadow.py --output /tmp/ucl-four-market-research.json
```

The dedicated pull-request workflow repeats these checks and asserts the CLI
still prints all four cases as HOLD. Automated tests validate **software
behavior**, not calibrated model accuracy, real-time prices, profitable EV
or actual team-lineup incorporation.

## Remaining blockers before expanding beyond research

1. Authoritative native UEFA/provider fixture IDs, second-source timestamp
   reconciliation, and independently authenticated starting XI provenance.
2. Explicitly licensed, time-stamped same-bookmaker prematch Asian handicap,
   *corner* and *first-half total* prices. The current core six-league 1X2
   feed does not certify coverage of these UCL markets.
3. Independently sealed prospective UCL goal, corner and first-half
   distributions with relevant out-of-sample scoring and conservative
   confidence bounds.
4. Original seven quality gates, independent finished-result admission and
   separate human authorization. Passing CI is not authorization for bets.

Related pending infrastructure: PR #306 adds European competition coverage
research and should be reviewed and merged **on its own merits**. This
sidecar does not duplicate or modify PR #306's collectors.
