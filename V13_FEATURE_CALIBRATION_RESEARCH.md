# V13 feature calibration research (HOLD/DISABLED)

Two independent optional challengers. No provider data, credentials or live capture is included. Use the existing V9.1 xG or V9.3 lineup capture and receipt format with additional owner-declared `competition_scope`, restricted to a single competition and consistent metric definition. No rights or point-in-time attestation is implied by local metadata. Do not commit licensed raw data. Prior-day available xG only, 120-day time decay, role-independent attack and concession rates with shrinkage; compare goals-only and geometric goals/xG blend on identical rows. Lineup effect is a bounded coefficient on the previously validated expected versus confirmed XI rating delta; no duplicate injury penalty. The declared baseline's exclusion of lineup information is not independently verified. No combined xG/lineup estimate or player-specific causal attribution.

Example after authorized data provision and fixing split before evaluating outcomes:

```sh
python -m ops.v9_feature_calibration --kind xg --capture matches.json --metadata receipt.json --split 2025-07-01T00:00:00Z --end 2026-07-01T00:00:00Z --output /tmp/xg-calibration.json
```

Use `--kind lineup` with the corresponding lineup capture. Both modes require at least 100 development / 50 assessment matches and all three outcome classes in each; lineup additionally needs 50 / 25 changed-XI cases. Development results must be available before split; assessment labels before end. Grid permits zero effect. Weekly paired interval if enough weeks. Fixed thresholds and half-life are research defaults, not optimized claims. No synthetic sample receives prospective credit. Actual archive and independently authenticated availability, competition identity and ratings needed. No live forecast, current quote, EV or deployment.
