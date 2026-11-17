# PR #458 — Original A + Penaltyblog Poisson/Dixon–Coles pre-match local handoff

Date: 2026-11-15 (UTC). Research only, **HOLD / DISABLED**. This is an **actual optional upstream model invocation in one process**, not yet a source-authenticated, continuously scheduled or deployed prediction pipeline.

## Why the new gate is necessary

GitHub PR #460 inspected seven original, Git-pinned compressed research pair archives on 2026-11-15. The real archive replay found **147 comparison rows across seven run attempts (not 147 unique matches)** with original A/market/AB-shrink/C-market-anchor probability vectors and **zero genuine upstream Penaltyblog native forecast snapshots**. The existing (separate) PR #458 could fit each optional model, but had no safe handoff binding an actual A input to *both freshly fitted* challengers before a future kickoff. Merely relabelling AB/C or performing today's hindsight fits would be invalid.

## New research-only entrypoint

`ops/penaltyblog_a_dual_prematch_capture.py` — `capture(payload)` or CLI:

```sh
python -m ops.penaltyblog_a_dual_prematch_capture \
  --input /approved/private/A-plus-lawful-history.json \
  --output /approved/private/new-unverified-3-model-capture.json
```

The file input must already exist locally with independently cleared usage rights. No scraper, bookmaker API or GitHub secret is used; no live provider request, data redistribution, actual money staking, automated model promotion or default network transport occurs.

The exact top-level input keys are `schema`, `production_recommendations`, `decision_cutoff_utc`, `original_a`, `historical_matches`; the schema is `football-king-prekickoff-a-penaltyblog-dual-handoff-v1` and the recommendation flag **must** be `DISABLED`.

- `original_a` must supply **source-native** `source_namespace`, `event_id`, `league_id`, `home_team_id`, `away_team_id`, `kickoff_utc`, `produced_utc`, `max_input_received_utc`, `model_id=poisson-shrinkage-unvalidated-v4.1`, `probabilities` in H/D/A order, and the three false/disabled trust fields. It must be a genuine original-model export established independently of this module; **do not derive native team IDs from free-form display names or invent an A source timestamp to fill a gap**. The current original public A archives generally lack all these certified source timestamps and IDs, so they cannot yet be plugged in automatically.
- `historical_matches` is the **existing exact PR #458 Penaltyblog offline input row schema**. The bridge rejects ambiguous native fixtures, duplicate matches, cross-league/provider IDs, future or unavailable results, fake goal counts and too few eligible training cases. Each model runs using the identical history and declared cutoff; the historical data's publisher identity and availability timestamps are still operator-claimed.
- The runner first validates the original A snapshot, its claimed last input timestamp and same native fixture identity, its maximum 120-minute age, the future kickoff with at least a 10-minute buffer, and model training data availability.
- The runner then observes **its own local wall clock** before fitting; calls the actual upstream `PoissonGoalsModel` via the existing optional bridge; checks local clock after it returns; calls `DixonColesGoalModel`; checks wall clock again. It requires monotonic timestamps, each model completed before the declared cutoff and at least 10 minutes before kickoff. Failure, missing upstream dependency, delay, mismatched model ID or probability, or invalid trust flag stops the entire handoff **without partial model outputs**. Clock comes from the executing process, not from the JSON. In tests, a fake deterministic clock is injected; those tests do not establish real time custody.
- If successful, the output remains **HOLD**, with a non-certified `unverified_triple_capture`: A original probabilities, two actually fitted challenger probability vectors, both local model start/finish instants, native fixture identity, declared cutoff, A/historical-input SHA256 digest labels, and `certified_prospective_samples=0`. A SHA256 of locally supplied data is not an authenticated signature or external TSA/Rekor time witness.
- The CLI reads only bounded regular files, rejects symlink/duplicate JSON/nonfinite/alias inputs, and only creates a **new**, owner-private mode-0600 output using exclusive-create. It never overwrites an archive or copies an old A/B/C snapshot. It saves no results/odds/EV and never prints raw probabilities in CI logs.

### Test and actual installed dependency

- `ops/tests/test_penaltyblog_a_dual_prematch_capture.py` includes adversarial contract/clock/identity/refit/atomic-failure tests with synthetic data and a fake model constructor; this is not proof of prediction accuracy.
- `ops/tests/penaltyblog_a_dual_real_smoke.py` runs **the actual installed `penaltyblog==1.13.1` Poisson and Dixon–Coles classes** on synthetic, purely fabricated old match history and a virtual future match within the current CI runtime's pre-kickoff window. It asserts that the result is still HOLD, zero certified samples, no authenticated wall clock, no data/quote source proof and no profit/EV. No real third-party match files or bookmaker quotes are fetched and no public forecast artifact is uploaded.
- Both run only under the research branch's `.github/workflows/penaltyblog-two-model-pipeline.yml` (separate synthetic and isolated-dependency jobs). The main scheduled workflow is unchanged. The real upstream wheel is installed only inside this isolated CI job.

## Scope and unresolved integration

This completes a **usable local interface for an independently supplied A research snapshot and legally usable training rows**, not an authenticated live original-A producer or automatic PR #460 merge. There is no independent, forward-looking original A native-ID/timestamp producer with all fields populated by a trusted source in the current workflow. Capture clocks are local and not externally attested. Published results, source rights, actual lineup/xG/market quotes and certified prospective sample identity remain unresolved.

The separate strict paired A/challenger/market timestamp and identity check is in [Draft PR #460](https://github.com/CHANCHUNWA1989/football-king-report/pull/460); the two Draft PRs must remain separate until independent integration review and a **verified, authorised** provenance producer exist. In particular, an aligned self-asserted JSON is not a certified A/B comparison or true model uplift.

Release is blocked by [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439): unprotected main and absent independent human approval. Do not merge, deploy, promote, recast legacy rows, backfill dates, compute fabricated EV or bypass the security HOLD gate.

## Actual-start history gate — 2026-11-17
- Reproduced a gap: history recorded after actual model start but before the declared future deadline could reach both fits.
- Reject any result-recorded instant later than the first actual local clock sample, before any constructor/fit or partial output.
- Two new test methods: four red first/last-row UTC/+08 cases; exact-start and one-microsecond-earlier boundaries remain valid.
- Verification: 51 related tests; full regression 2,923 tests, zero failures, two locally absent optional-dependency skips; compileall/diff check passed.
- One read-only QA found no code issue; it is not independent human approval. Existing source/native-ID/probability/clock gates remain unchanged.
- The already frozen live pilot satisfies this extra guard; no source data, forecasts or fit outputs were regenerated or relabelled.
- This checks claimed availability against local execution only, not publisher truth, independent time, identical A information or positive EV; Draft/HOLD/DISABLED and certified count0 remain.
