# PR #458 — Original A shadow native-ID to Penaltyblog two-model local handoff

2026-11-15. DRAFT / HOLD / DISABLED. Original A report schema adaptation and genuine upstream model execution in isolated research only; no production rollout.

## Concrete existing original A fields — no retroactive matching

Inspected `ops/shadow_forecast.py` and `ops/source_fixture_identity.py`. The original A model reports its generated shadow output as `football-king-uncalibrated-shadow-1`. An ordinary live run may include a `generation_clock` with actual local started/completed UTC; individual current-batch forecasts have `prediction_utc` equal to the completed clock. OpenLigaDB Bundesliga rows can also include a `native_fixture_input` extracted by the original producer from **the same HTTP response** as the normalized scheduled fixture (native `match_id`, `home_team_id`, `away_team_id`, `league_id`, `league_season` and a `source_response_sha256`). The corresponding `sources` record carries `captured_utc` and a matching source response hash.

**Critical limitations:** these observed values are self-reported original-run metadata, NOT independent evidence of original publisher authenticity, external UTC clock custody, source licensing, or archived source bytes. The live `native_fixture_input` explicitly states `source_identity_authenticated=false`, `source_capture_authenticated=false`, `raw_input_durably_archived=false`, `native_ids_used_as_model_features=false`, and `eligible_for_model_scoring=false`. Public historical settled `ab`/`c` are not Penaltyblog forecasts. Never backfill legacy source IDs or timestamps from current observations.

## New code and technical boundary

- `ops/penaltyblog_a_shadow_native_handoff.py` has `link(shadow, history, event_id, cutoff_utc, clock=None, model_factories=None)`. It checks the original A report's disabled/shadow-only flags, live (not replay) local generation clock, exact per-prediction completion time, unique canonical OpenLigaDB event ID, same-source raw response digest, bounded source capture clock, native fixture/team/league IDs from the same response, observed prior A model version and probability validity. It refuses missing, conflicting, bool-typed, fake authenticated or guessed IDs, ambiguous sources, replay shadow reports and post-kickoff cutoffs. Only a Bundesliga / `bl1` same-response native-ID case can pass the current adapter, because the other leagues do not have that strict original binding in this producer.
- The adapter maps **native integer IDs already present in the original observation** to text IDs for the offline `ops/penaltyblog_a_dual_prematch_capture.py` bridge. It never matches displayed team names, fetches a future result, or synthesizes a native ID. It uses `prediction_utc` = the original A's own declared batch completion (not a new timestamp), and `max_input_received_utc` = the original source's preexisting declared `captured_utc`. A later externally chosen decision cutoff must be after the A completion, before kickoff and at least ten minutes before kickoff; both model refits must complete by cutoff according to the local process clock.
- The adapter then **actually invokes** the optional Penaltyblog Poisson and Dixon–Coles models through the prior 3-model capture interface using identical, already authorized and explicitly unverified local historical rows. If either fit fails, a clock rewinds or any source/history ambiguity exists, the entire report remains HOLD without any `unverified_triple_capture` or partial model scores.
- Successful local matching is still `status=HOLD`, with only a `unverified_triple_capture`, `certified_prospective_samples=0`, `positive_ev_verified=false`, `production_recommendations=DISABLED`. The source response digest is a locally claimed SHA256; it does not prove that raw provider bytes were archived or signed. The original training-observation digest is retained as an *unattested* reference. No market price, lineup, xG or EV is collected.
- Private CLI supports separate already-existing local `--shadow` report file and `--history` original authorized historical rows file, `--event-id`, `--decision-cutoff-utc`, `--output`. Input size is bounded and symlinks/duplicate JSON keys rejected by the existing reader; output can only be created new at mode 0600, not overwritten. CI never uploads an actual private capture.

Example isolated research usage (both files must contain appropriate actual values and be legally available):

```sh
python -m ops.penaltyblog_a_shadow_native_handoff \
  --shadow /private/original-A-shadow.json \
  --history /private/rights-cleared-native-history.json \
  --event-id openligadb:123456 \
  --decision-cutoff-utc 2026-12-01T18:00:00Z \
  --output /private/NEW-a-poisson-dc-unattested.json
```

That command is an **interface example only**, not a claim that the illustrative event ID, history or timestamp exist. Do not execute it with arbitrary guessed inputs.

### CI and test boundaries

- `ops/tests/test_penaltyblog_a_shadow_native_handoff.py`: synthetic contract tests for no fuzzy name mapping, swapped native team order, duplicate fixture, original live generation clock and source capture integrity, invalid native ID/hash, bad probabilities, unauthorized history, late refit, symlink/alias and no-overwrite output.
- `ops/tests/penaltyblog_shadow_native_real_smoke.py`: actual isolated installation `penaltyblog==1.13.1` and genuine upstream Poisson/Dixon–Coles model fitting on synthetic source-shaped shadow and prior-result rows. Its *only* purpose is end-to-end schema compatibility; it cannot authenticate external source bytes, local timestamps, data rights or OOS predictions.
- `.github/workflows/penaltyblog-two-model-pipeline.yml`: add both checks to existing research-only CI, without changing live main workflows.

## Still blocked

A genuine original A producer's signed/immutable raw source identity record with third-party timestamp witness, legitimate original results history **with valid source rights**, a real forecast pre-kickoff capture in an authorized environment, and independent settlement/market quote provenance are **NOT established** by the local connector. The current native input explicitly says raw_input_durably_archived=false and is not suitable to be certified. Existing `main` did not get a Penaltyblog installation or new background scheduled capture.

Keep Penaltyblog separate from main, and keep PR #460's comparison stage separate until independent audit and true forward data are available. The governance blocker [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439) (main protection and human independent approval) is unresolved. Absolutely no valid assertion of accuracy lift, ROI, EV, certification, betting readiness or model promotion is possible at this stage.
