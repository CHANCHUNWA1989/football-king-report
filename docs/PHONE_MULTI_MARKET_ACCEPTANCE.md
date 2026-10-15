# Football King: iPhone zero-credit acceptance

Research branch: `research/recommendation-evidence-gate-20261015`
Draft review: https://github.com/CHANCHUNWA1989/football-king-report/pull/188

## What is verified
- Python syntax and private multi-market quote tests run in CI.
- Three-market sample is opt-in, single league, quota-guarded.
- Raw bookmaker prices and provider secrets must never be committed.
- Production recommendations stay DISABLED.

## Run without API credits
The dry-run command can run on any Python 3.12 environment:

```sh
python ops/opt_in_multi_market_sample.py --league epl --dry-run --output /tmp/football-king-dry-run.json
```

The report must say `DRY_RUN`, `api_requests_made: 0`, and
`production_recommendations: DISABLED`.

## iPhone GitHub Actions caveat
GitHub manual workflow_dispatch normally requires the workflow to exist on the
repository default branch. A workflow committed only to this draft PR may be
tested by push/PR CI but may not appear as a manual Run workflow button.
Do not merge the draft PR merely to enable the button; review first.

## Future private sample (not yet deployed)
The opt-in live sampler requires THE_ODDS_API_KEY in a private environment,
explicit --ack-credit-cost, and sufficient verified remaining credits. It
requests one league and h2h/spreads/totals, and only emits aggregated audit
counts. Never print provider URLs, raw odds, bookmaker names or secret values.

## Acceptance before recommendations
1. Verify provider market entitlement and actual returned market sides.
2. Accumulate timestamped independent model forecasts before kickoff.
3. Compare predictions against settled outcomes out of sample, by market.
4. Check calibration, data leakage, stability, and uncertainty.
5. Require human approval before any production recommendation.
