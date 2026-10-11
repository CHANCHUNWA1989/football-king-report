# Football King: registered point-in-time market-anchored challenger C

**Registered 11 October 2026; research-only. This is not a performance claim.**

## Hypothesis
The existing Poisson 1X2 A model has shown excess confidence in a small
seven-case settlement set and higher mean Log Loss than the earlier de-vigged
market consensus. Candidate C tests whether the original model adds any value
to the market prior without trusting the model's extreme probabilities.

Fixed prospectively, C = **0.25 * A + 0.75 * earlier market consensus**.
This numerical weight is a pragmatic untuned comparison, *not* fitted to or
optimized on the seven old games. It may perform worse than market alone.

## Strict creation and evidence
- Creation: `ops/market_pair.py` only after a single valid league-scoped
  matched fixture, bounded quote age, actual `market_updated_utc` before
  `market_snapshot_utc` before `prediction_utc` before kickoff.
- The same prospective snapshot stores A, market, C, version, safety flags,
  and observation timestamps together in `research_pairs/...json.gz`.
  Raw commercial prices and private API keys are never included.
- `ops/forward_validation.py` accepts C metrics only if the *sealed* version
  and probabilities match the fixed formula to rounding tolerance.
  Older settled predictions with no C **remain C-unscored**; an old forecast
  is never re-derived from already-known outcomes to inflate the challenger
  sample count. Malformed C archives do not settle.
- `ops/evidence_merge.py` independently refuses C tampering and preserves
  the original sealed case on concurrent updates.
- `validation.json.fixed_market_anchored_challenger_c` and
  `research_center.json.*.market_anchored_c_research` compare C, A and
  market on the **same** future settled C-bearing fixtures, via Log Loss,
  Brier and top-choice hit counts, disclosing full actual sample n.
- No re-training of A, no model or price lookahead, and no automatic promotion.
  Production remains DISABLED. Source results are not independently certified.

## Acceptance later
An initial C advantage in tiny unauthenticated samples would not justify
any betting recommendation. Evaluate over 300 valid independent sealed samples
and at least 12 week blocks across multiple leagues, with honest audit of
calibration, reproducibility, conditional performance, uncertainty, and
executable market odds. Compare against *market alone*, not merely A. A
challenger that only copies the market must not be called profitable.
Do not retrospectively tune blend weight or cherry-pick fixtures.
