# P0 #569 — iPhone settlement two-view cutover dry-run (2026-11-23 HKT)

**Scope: research-only / no live workflow modification / HOLD / DISABLED.**

## Confirmed current-route problem

On current `main` `.github/workflows/football-king-iphone.yml`:
- Lines around 295–303: `forward_validation.py --previous evidence/settled.json --output "$RUNNER_TEMP/settled.json"` produces an in-run cumulative snapshot.
- Around line 535: `forward_daily_scorecard.py --input "$RUNNER_TEMP/settled.json"` feeds the iPhone *daily research scorecard*.
- Around lines 499–515: `python -m ops.public_readiness_site --settled evidence/settled.json` feeds the iPhone *official-readiness* panel from the old **main-branch** snapshot.

These two iPhone views may diverge whenever new unverified research results are in the run-scoped cumulative file but not yet safely preserved in `main`. An archive branch cutover must not preserve this split.

## What was added in research PR #571

- `ops/mobile_settlement_parity_preflight.py` uses the **real** `ops.public_readiness_site.build` and `ops.forward_daily_scorecard.build` functions, not a hand-made replacement for their count logic. It requires the complete legacy history, forbids changed/deleted original rows, independently runs each builder against proposed new in-memory cumulative evidence, verifies safety invariants, and emits only a bounded receipt without writing any mobile page or workflow.
- `ops/forward_daily_scorecard.py` import path compatibility was adjusted so its original direct script invocation **and** package imports both work, without altering report calculation.
- `ops/tests/test_mobile_settlement_parity_preflight.py` contains ten offline tests. It uses the **actual checked-in research-only** `evidence/settled.json` (minimum 105 old observations), current quality/market aggregate files, and a **clearly synthetic extra row** in memory (never a real fixture, verified FT, or bettable edge):
  - Legacy replay: both builders report the original case count, no historic file bytes changed.
  - One synthetic candidate row: current mixed-source workflow would report legacy `N` on official readiness versus `N+1` in daily scorecard: **HOLD_CURRENT_WORKFLOW_SOURCE_SPLIT**. *If both* builders were given the identical candidate, they agree on `N+1` while remaining HOLD/DISABLED; **this is a simulation and not a deployed switch**.
  - Missing or changed historic rows, duplicate keys, any `ENABLED` flag are rejected.
  - CLI exits **nonzero** when split is found, without changing `main` or the iPhone site.

### Offline usage

```bash
python -m ops.mobile_settlement_parity_preflight \
  --legacy evidence/settled.json \
  --candidate /path/to/locally-inspected-cumulative-research.json \
  --gates sources/seven_quality_gates_latest.json \
  --market market/latest.json
```

A candidate path is **untrusted**. This preflight does not authenticate the candidate's remote-branch owner, immutable Git archive receipt, upstream official result source, or any licensed odds. Require separate successful `archive_remote_ref_gate` + pinned-tree checks before a prospective reader cutover. The legacy 105 samples remain unverified historical research, not certified football finals.

## Explicit release gate and remaining work

1. Authorized owner and independent reviewer must agree on **one** canonical, authenticated run-scoped settlement file used by *all* iPhone consumers. The existing `--settled evidence/settled.json` direct-main path in official-readiness must be explicitly migrated alongside any other producer/consumer.
2. Re-run both actual mobile report builders from that same pinned and authenticated input under a synthetic remote canary; prove count, sample-key preservation, HOLD/disabled status and HTML/JSON readiness. Do **not** use missing evidence or count-only parity to prove authentic results.
3. Diagnose existing five failed `evidence/settled.json` GitHub Contents PUT attempts, and migrate **both** existing direct-main archive jobs. No bypass, no direct-main write under main PR-only Rulesets.
4. Owner provisions an appropriate isolated archive branch with permission scope and retention controls; independently approved synthetic canary + rollback then review of #439. PR #571 remains Draft/unmerged until reviewer approval. Rights/OOS #452 unresolved.

Neither the static audit nor this offline parity test authorizes any production change, source rights, betting recommendation or positive EV. All remain `HOLD / DISABLED`.
