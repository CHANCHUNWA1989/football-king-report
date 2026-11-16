# Football-King — immutable five-model Nov 21 Bundesliga paired postmatch preflight

**Pre-registered on 2026-11-17 HKT, before either match starts.**
**Research-only Draft / HOLD / production DISABLED.**

## Exact already frozen probabilities — never refit after kickoff

The **original local pre-kickoff** five-model forecast comes from
`ops/research_manifests/dynamic_five_model_forward_local_20261117_pinned.json`,
first Git commit `24e95a63b1f54cfa64b2ccd34705183aa6d2c816`, its **unmodified Git
blob SHA1** `087a3c3277dc07b0f7936b06dbcfac2f2df8d738`.
Original true-time local GitHub run:
https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/43912691040.

Exactly two frozen matches, both still future at freeze:
- `openligadb:83237`: Bayern München vs 1. FC Köln,
  **2026-11-21 03:30 Hong Kong time** (2026-11-20 19:30 UTC).
- `openligadb:83238`: Bayer Leverkusen vs SC Paderborn 07,
  **2026-11-21 22:30 Hong Kong time** (2026-11-21 14:30 UTC).

The source was OpenLigaDB one-GET, 81 historical finished matches. A,
Poisson, DC, bivariate and dynamic all emitted a same-source/cutoff local
1X2 vector, but **publisher authenticity, original historical result
release times, independent kickoff witness, xG, market odds/actual prices
and independent third-party time certification are NOT available**.

## Fixed BEFORE results: postmatch evaluation protocol

The new `ops/five_model_pinned_postmatch_audit.py` is deliberately offline
and immutable:

1. Reject any forecast bytes failing the original Git **blob hash**, missing
   either event ID, malformed probabilities, different source history,
   changed native identity or any model completion after kickoff.
2. **Require both fixtures together**: 2 publisher observations per fixture,
   90-minute **FT** final, exact source fixture/team/kickoff identity and
   at least 90 minutes after kickoff. Reject missing, duplicate, partial,
   abandoned, live, suspended, conflicting or suspicious result timestamps.
3. Reuse repository's existing `postmatch_result_status_guard`:
   publisher name and **HTTPS host must differ**. That is only a metadata
   corroboration, **not** independent publisher authentication or official
   result verification; external fact-checking remains outstanding.
4. For *all five* original untouched 1X2 vectors compute full-time outcome,
   top-direction hits, mean **3-class Brier** and mean **log loss** over
   the same **n=2**, with no model exclusion after the scores.
5. For the **two** models with genuinely frozen joint Asian markets
   (`bivariate` and `dynamic` only), compare hypothetical **Over
   2.75** and **home AH -0.25** exact five-grade settlement Brier and
   log loss. Use already tested existing AH and total settlement functions.
   **Do not reconstruct** old A/Poisson/DC unsealed AH/OU scores
   after the outcome or call those prices offered by a bookmaker.
6. No model selection, calibration claim, confidence interval, EV, ROI,
   Kelly staking or risk promise on **two** matches. All result metrics
   remain descriptive. Even when supplied sources agree, `status=HOLD`,
   `positive_ev_verified=false`, `certified_prospective_samples=0`.
7. If either result has missing/conflicted authenticity evidence, return
   **HOLD without any partial model scorecard**. Separate official-source
   or independently witnessed verification remains a human/evidence review
   gate. No claim of certification from a JSON flag.

This **no-cherry-picking** protocol is itself frozen **before outcomes**.
No hyperparameters or historic probabilities may be reestimated from
either November 21 result. The test fixture scores [2-0, 1-1] under
`ops/tests/test_five_model_pinned_postmatch_audit.py` are **synthetic
unit-test fixtures** and MUST NEVER be presented as actual match results.

## Run preflight NOW (genuine sealed forecast only, ZERO results)

```bash
python -m ops.five_model_pinned_postmatch_audit \
  --manifest ops/research_manifests/dynamic_five_model_forward_local_20261117_pinned.json \
  --output /tmp/real_pre_match_preflight.json
```

The GitHub Actions workflow
`.github/workflows/five-model-pinned-postmatch-preflight.yml`
checks the **exact Git blob**, compilation, adversarial synthetic
test fixtures, and actual genuine forecast-only preflight. The output
must always show `scored_matches=0` before real FT evidence.

## After BOTH Nov21 matches: require genuine reviewed evidence

Prepare one independent `results.json`:

```json
{
  "schema": "football-king-five-model-two-publisher-ft-input-v1",
  "observations": [
    {
      "event_id": "openligadb:83237",
      "publishers": [
        {
          "publisher": "ACTUAL_PROVIDER_A",
          "source_url": "https://a-real-source.example/specific-match-page",
          "league": "bundesliga",
          "home": "FC Bayern München",
          "away": "1. FC Köln",
          "kickoff_utc": "2026-11-20T19:30:00+00:00",
          "home_goals": 0,
          "away_goals": 0,
          "match_status": "FT",
          "observed_utc": "2026-11-21T00:00:00+00:00"
        },
        {
          "publisher": "ACTUAL_PROVIDER_B",
          "source_url": "https://another-independent-source.example/specific-match-page",
          "league": "bundesliga",
          "home": "FC Bayern München",
          "away": "1. FC Köln",
          "kickoff_utc": "2026-11-20T19:30:00+00:00",
          "home_goals": 0,
          "away_goals": 0,
          "match_status": "FT",
          "observed_utc": "2026-11-21T00:00:00+00:00"
        }
      ]
    }
  ]
}
```

**The example above is NOT usable real evidence**: all scores, providers,
domains and timestamps are fictional/placeholder. The actual input MUST
contain both events (83237 and 83238), exactly 2 independently reviewed
true sources each, genuine 90-minute scores and authentic observation
timestamps. It is intentionally incomplete to prevent accidental
fictional results. Existing postmatch tasks may provide the verified
evidence, but must not rewrite the sealed original forecast.

Then, and only then:

```bash
python -m ops.five_model_pinned_postmatch_audit \
  --results /approved/private/reviewed-two-fixture-ft.json \
  --output /approved/private/new-five-model-postmatch-report.json
```

**This script never fetches the scores on its own.** Review all original
source URLs and score classifications separately before calling the
result a corroborated research score. The output remains HOLD and
not independently certified.

No new automatic GitHub scheduling or betting execution is created;
the user's existing scheduled research reviews are separate.
