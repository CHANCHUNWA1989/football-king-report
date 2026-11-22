# 足球王者 VNext 第四階段：研究來源交叉核對與私有證據入口

2026-11-22 HKT · **Draft / RESEARCH_ONLY / HOLD / DISABLED**

## What was actually built

- `ops/vnext_stage4_evidence.py` is a pure offline safety gate (no HTTP, scraping, paid API, credentials, bookmaker recommendation or EV). It accepts pre-prepared regulation-time result rows from two *named* sources and reports overlap, agreements, disagreements and blockers; it **never** certifies independence.
- The private bundle validator checks fixture identity, bytes-to-SHA256 equality, unique JSON members, source/update timestamps, historical xG row format and a chronological `xG -> forecast -> odds -> kickoff` handoff. It checks caller-supplied **claims**; vendor authorization, upstream origins, actual recorded time and execution are **not** proven.
- All outputs are aggregate/redacted and remain `HOLD`, `production_recommendations=DISABLED`, `verified_positive_ev=false`, with no recommended stake.
- This does not replace existing `ops/market_quote_gate.py`, `ops/private_forecast_quote_pair.py`, or the stage-3 three-market matching tool; quote/market integration is explicitly blocked until those already-present gates consume real legally obtained private data.

## What was observed in retrospective research

OpenFootball 2026/27 Italy JSON 50 completed matches and a prior archived open-matchday Italy CSV sample of 110 completed matches, last result dated 2026-11-08, were compared **from locally reconstructed prior score vectors**. There were 50 shared fixture/date identities, 50 equal full-time scores, zero conflicts, and 60 rows appearing only in the latter sample. Reconstructed vectors are not new original provider byte archives and are not externally timestamped. The initial upstream histories, independent original regulation-time final, actual kickoff and publication provenance were **not verified**; certified forward samples stay **0/300**.

Source URLs (do not copy data into the public repository):
- https://github.com/openfootball/football.json/blob/master/2026-27/it.1.json — OpenFootball CC0 data.
- https://github.com/oladeeayo/open-matchday/blob/master/data/ITA_1_serie-a/results_2627.csv — open-matchday compilation; upstream provider rights remain reserved; raw redistribution and commercial use require separate review.

The open-matchday source identified `fixturedl` in the historical rows. Source spelling and distinct collection repositories do not establish independent original upstreams.

## Test command and release boundary

```bash
python -m unittest -v ops.tests.test_vnext_stage4_evidence
python -m compileall -q ops/vnext_stage4_evidence.py ops/tests/test_vnext_stage4_evidence.py
```

- 22 local focused tests passed on 2026-11-22 (synthetic error cases; not public live odds/xG authentication).
- CI and independent code review required for this exact GitHub head. No merge or deployment approval from local tests.
- Never publish private vendor bytes, tokens, sportsbook quotes, private signatures, bookmaker IDs or personal keys into GitHub, Actions artifacts or logs. Use private access-controlled storage, retain source-native event IDs and original rights/lineage documents.
- Before any prospective betting status: obtain licensed per-fixture xG and source publication times, bookmaker market-level native snapshots, externally witnessed forecast and result evidence, source upstream independence and actual regulation FT, valid chronological paired out-of-sample scoring and confidence intervals, human release review, and independently approved branch protection. Existing 0/300 counter must not be advanced by retrospective overlap.