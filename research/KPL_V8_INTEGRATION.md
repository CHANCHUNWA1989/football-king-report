# KPL V8 BP evidence adapter — research only

This change is an **isolated KPL research adapter** in the football-king-report repository. It does not change any existing football, basketball, or quant model; does not enable the website, scheduled runs, betting tips, or execution; and does not claim to have verified November 3 match BP or betting value.

## Reuse decision
- Reuses **existing** `shared.source_freshness.check_source` to reject stale/future timestamps.
- Adds only `research/kpl_v7_bp_evidence.py` and `ops/tests/test_kpl_v7_bp_evidence.py` with standard-library code.
- Intentionally **does not** pass KPL events into `shared.unified_prediction_ledger`, which currently supports only `football`, `basketball`, `quant`. Never relabel esports as football to bypass the whitelist.
- Later phases may add a coordinated `esports` contract across repositories; it must remain shadow/research only and be independently tested.

## Input contract
`audit_bp_snapshot(snapshot, previous_games, now_utc="2026-11-03T12:00:30Z")` accepts:
- `event_id`: provider-stable ID (no fuzzy team-name matching).
- `game_number`: integer 1–7; `team_ids`: two stable IDs, consistently ordered across games.
- `side_by_team`: exact two teams mapped to one `blue` and one `red`.
- `picks_by_team`: five unique non-empty hero IDs per team.
- `bans_by_team`: list of banned hero IDs per team, with no duplicate or overlap with picks. **Ban count is NOT independently checked against a rulebook.**
- `bp_complete`: explicit completion attestation; `source_authenticated`: external human/provider attestation, **not an authentication result computed by the code**.
- `source`, `published_at`, `observed_at`: source label and timezone-aware publication/capture clocks. Captures must be fresh under the configured threshold.
- `previous_games`: ordered complete games 1 through N-1, all matching the event/team IDs and externally attested.

Games 1–6 reject **same-team** hero reuse. Game 7 allows reuse as peak duel, but still requires a complete preceding history. This check does not authenticate tournament rules (patch-specific hero-form exceptions, bans format, side selection, or draft legality beyond these constraints), nor actual match data.

The adapter returns `VALIDATED_RESEARCH_INPUT` only for structural/time-valid data carrying external attestation; it always returns `research_only=True`, `live_execution_allowed=False`, and `external_authentication_not_proven_by_code=True`. Any fail-closed reason returns `HOLD`. Do not interpret the status as official BP verification.

## Synthetic tests / acceptance
```bash
python -m compileall -q ops research
python -m unittest discover -s ops/tests -p 'test_kpl_v7_bp_evidence.py' -v
python -m unittest discover -s ops/tests -q
```
The narrow synthetic tests cover a valid snapshot, repeat hero, game-7 exception, omitted history, unauthenticated source and prior game, stale and naive timestamps, duplicate cross-team pick, inconsistent side input, and pick/ban conflicts. All real KPL data and end-to-end integration remain unavailable / unverified.

## Planned integration (not implemented)
1. Authenticate provider identity and source publication/capture timestamps independently; record official match and per-game IDs.
2. Obtain licensed, complete bans/picks and map stable hero IDs; verify actual 2026 KPL patch/rules.
3. Capture verified minute-by-minute gold differential, towers, neutral objectives and side selection.
4. Extend shared ledger with explicit `esports` type only after cross-repository compatibility review; preserve event-level, game-level, and prediction-time lineage.
5. Use chronological holdout, same-information-cutoff baselines, Brier/log loss, calibration curves, and uncertainty before describing predictive accuracy.
6. Keep `production_recommendations=DISABLED` / `HOLD` and no verified positive EV without independently authenticated executable quotes and calibrated conservative probability bounds.
