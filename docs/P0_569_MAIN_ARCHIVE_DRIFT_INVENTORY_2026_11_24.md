# P0 #569 — actual main/archive divergence inventory and read-only preflight

**2026-11-24 00:27+ HKT research checkpoint · Draft PR #571 · HOLD / DISABLED**

## 1. Fresh actual GitHub comparison (read only)

At the referenced GitHub API observation:

- Real `main`: `74913afd8ad92e49b05f2832a2d05e33781abd01`, `protected: false`.
- Actual bootstrap `refs/heads/research/forward-provenance-archive`: `3ce493fbeb9bfea29af1b93064a085afe8efb280`.
- GitHub compare `3ce493fb...74913afd`: `status: ahead`, **13** commits added to `main`, **0** behind relative to archive bootstrap; **26** file-level changes.
- Classification by literal path/status: **20 added historical/provenance artifacts**, **0 historical deletes/rewrites observed in this particular compare**, **6 modified latest/status pointers**, **0 unclassified paths**.
- No claim that the historical blobs are source-authenticated, independently signed, or suitable as sportsbook evidence. No inference of data completeness outside these two pinned SHAs.

### 20 added historical artifacts

| Area | Count | Source example or run family |
|---|---:|---|
| `forecast_provenance/` | 10 | `2026/11/23/45186921642-1/` evidence and synthetic check receipts |
| `history/`, `shadow/`, `research_pairs/`, `verification_slates/`, `worldwide_shadow/` | 5 | `2026/11/23/45186921642-1.json.gz` |
| `sources/history/` | 1 | `2026/11/23/45185933291-1.json.gz` |
| `sources/live_germany/history/` | 1 | `2026/11/23/14-45199169113.json.gz` |
| `sources/six_league_quality_history/` | 3 | `2026/11/23/45182156878-1/` three gated research gzip documents |
| **Total** | **20** | Historical original-byte preservation must be separately reviewed |

### 6 changed mutable pointers

`sources/hkjc_tipsme_free_latest.json`, `sources/latest.json`, `sources/live_germany_latest.json`, `sources/seven_quality_gates_latest.json`, `sources/six_league_fixture_overlap_latest.json`, `sources/six_league_free_latest.json`.

These values may have producer freshness and consumer contract constraints and must not be naively merged, copied to an archive, or republished without documented source/reader parity.

## 2. New repeatable local-only guard

- `ops/archive_branch_drift_inventory.py` accepts **two exact 40-hex commit object IDs** and a **local Git worktree root**. It uses exclusively read-only `rev-parse`, `cat-file`, `merge-base` and `diff` operations with a sanitized Git environment.
- Strict 256-path, 64-KB output and path-status validation; no network Git operation, clone, fetch, worktree, push, checkout, branch creation, reset, merge or file write.
- Separately inventories `historical_added`, `historical_mutated_or_removed`, `mutable_publisher_change` and `unclassified_change` with exact reviewed paths and a deterministic digest for a reviewer. Detects ancestor, descendant, same-commit and divergence relationships.
- CLI **always exits nonzero** and sets `status=HOLD_DRIFT_REVIEW_AND_HOSTED_POLICY_REQUIRED`, `archive_write_authorized=false`, `main_ruleset_activation_authorized=false`, `production_recommendations=DISABLED`, including zero diff.
- `ops/tests/test_archive_branch_drift_inventory.py` provides nine **offline real-Git tests**: 20/6-like categorization, rewrite/delete rejection class, diverged history, same-SHA still HOLD, invalid commit object/absent common history, nonroot, nonzero CLI with sanitized errors, and no mutating/network commands.

**Important distinction:** The 13/20/6 figures above were derived from an **actual connected GitHub read-only compare of the pinned real refs**. The new Python module has been exercised only on temporary local Git fixtures; it has NOT authenticated current remote heads, and it MUST NOT be represented as an automated deployed reconciliation job.

## 3. Source and consumer migration blockers

1. Save immutable history from the pinned current-main tree as a **reviewed manifest** before changing publisher destinations. Avoid overwriting or omitting 20 newly added files, and account for future main changes with fresh SHA checks.
2. For six mutable pointers, audit producer freshness, active triggers, site/iPhone readers and redaction/licensing before designing any new publication route. Archive history and public latest snapshots need separate write contracts.
3. Four actual direct-main archival job blocks and fourteen Contents API mutation-indicator workflow files are still deployed on `main` (15 distinct workflows with `contents: write`).
4. Actual hosted archive ref is bootstrapped but not independently verified for non-force, non-delete and actor isolation. `main` remains unprotected; Rulesets `[]`; 0 independent PR reviews. Hosted official writes are hard locked in the research branch.
5. An independent nonauthor reviewer and owner/admin must attest effective GitHub protection (including no-bypass actors) and a principal unable to write `main`. Only then may a **separately approved synthetic-only hosted canary** be considered. No self-approval, owner-token workaround, direct-main fallback or merge of this Draft PR.

## 4. Decision

**Inventory: COMPLETE for this SHA pair only. Remote archive custody, real replay/read parity, producer cutover, current iPhone publication, licensed real market source, outcome verification, OOS profitability and positive EV: NOT VERIFIED.**

**`HOLD / DISABLED`. PR #571 Draft/unmerged; issues #569, #439 and #452 remain open.**
