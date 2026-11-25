# P0 #569 — Whole-workflow fleet write-risk inventory (2026-11-23 HKT)

**Offline research only; always HOLD / DISABLED. No main Ruleset activation, workflow rewrite, provider access, betting, or release authority.**

## Frozen audit evidence

Pinned default-branch `main` SHA: `3ce493fbeb9bfea29af1b93064a085afe8efb280`.

A read-only GitHub Contents directory listing showed **63** `.github/workflows/*.yml` files. New research module `ops/workflow_fleet_write_inventory.py` scans every checked-in YAML workflow in bounded standard-library-only mode (max 128 workflows, 1 MB per file, 8 MB total). Each input gets an SHA-256 and only safe filename/line-number indicators are retained. No raw lines, data credentials or archive content appear in the receipt.

At exact PR research head `6ac7b1c79b089cafcfa10a9b9bdaf166e1adf06a`, [Safety CI #45173596377](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45173596377) regression job `137689047325` emitted the bounded `P0_569_FLEET_SUMMARY` evidence:
- **63 workflow files scanned**.
- **2 workflows with explicit `git ... push origin HEAD:refs/heads/main`**: `football-king-iphone.yml`, `four-model-shadow-daily.yml`.
- **14 workflows containing GitHub Contents API mutation commands** (potential default-branch writes; inspect branch arguments and actual authorization before attributing writes).
- **15 workflows requesting `contents: write` permission**. Permission alone is NOT proof of a write.

### Contents API mutation indicators — 14 files

1. `football-king-asia-apis.yml`
2. `football-king-bsd-free.yml`
3. `football-king-german-live.yml`
4. `football-king-hkjc-free-research.yml`
5. `football-king-iphone.yml`
6. `football-king-japan-free-market.yml`
7. `football-king-odds.yml`
8. `football-king-research-extensions.yml`
9. `football-king-secondary-sources.yml`
10. `football-king-six-free-upgrade.yml`
11. `football-king-weather.yml`
12. `football-king-weekly.yml`
13. `football-king-wide-free.yml`
14. `private-all-market-research.yml`

### Additional permission-only class

The 15 workflows with `contents: write` comprise the preceding 14 plus `four-model-shadow-daily.yml`, which has explicit main Git pushes.

## Test and safety evidence

The following was checked for exact head `6ac7b1c79b089cafcfa10a9b9bdaf166e1adf06a`:
- [Safety regression #45173596377](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45173596377): **all 7 fleet-inventory tests PASS**, **2,445 ops tests complete**, **117 V4.1 compatibility tests complete**, SUCCESS.
- [Failover #45173596393](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45173596393), [Repository Safety #45173596549](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45173596549), [Offline 1X2 #45173596443](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45173596443), [Unified Ledger #45173596392](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45173596392): SUCCESS.

Invoke the read-only diagnostic locally from a checked-out research PR:

```sh
python -m ops.workflow_fleet_write_inventory --workflows .github/workflows
```

**Exit code 1 is intentional even if no write strings appear**: this is a veto-style diagnostic, not a green production gate. Its status is always `HOLD_WORKFLOW_FLEET_CUTOVER_UNVERIFIED` or a bounded failure. `main_ruleset_activation_authorized=false`; `production_recommendations=DISABLED`.

## Limitations and next independent acceptance

This is a **literal string/static indicator scan**, not a complete YAML/shell parser, effective token-scope audit, GraphQL/GitHub App admin audit, third-party action source review, Git history retention proof or proof a workflow actually ran. It may miss aliases, generated commands, composite/reusable workflows, indirect shell scripts, REST calls in Python, and any writers outside `.github/workflows`. Even an empty scan can NEVER authorize a no-bypass Ruleset. The real `research/forward-provenance-archive` branch has not been verified/provisioned; no real synthetic-only authenticated archive canary, reader cutover, independent review or provider-rights certification exists.

Required next step: independently inspect and categorize each of the 15 identified workflows (target branch, credentials, data class, writers and downstream readers), plus other indirect code paths, then design their separate protected-branch or immutable-store migrations and fail-closed read compatibility. Do not exempt a write-capable GitHub bot from a no-bypass main Ruleset without an explicit independent governance decision. Preserve current original main archive and 105 research-only settlement observations until verified migration.

**PR #571 remains Draft/unmerged; issues #569/#439/#452 remain blockers. HOLD / DISABLED.**
