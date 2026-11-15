# DS Bot pinned upstream install/test rehearsal — research only

2026-11-15. Follows Draft PR #471 (offline research-note handoff gate), **not** an extension of main/production.

## Specific verified upstream inputs

- Upstream: https://github.com/Fei2411/DS-Bot
- Git SHA **a66cc737cfb6c3d8a2597e748cded6cab1206dd3** (reviewed publicly); upstream `ds-bot/package.json` version **0.3.6**; published release `v0.3.6`.
- Upstream project `LICENSE`: **Apache-2.0**; `NOTICE` records third-party code/DeepSeek Harness obligations. No source vendoring/copying in this PR.
- Their own `.github/workflows/test.yml` uses Node.js 24 and `@deepseek-ai/dsh@0.2.2-rc.1` with a mock harness; those versions are explicitly pinned in our isolated smoke.
- Actions checkout and setup-node actions are SHA-pinned; node package installs use upstream lockfile, with lifecycle scripts disabled.

## What this PR actually does

Adds **`.github/workflows/dsbot-pinned-upstream-smoke.yml`**:

1. In an **ephemeral GitHub runner** with `permissions: contents: read`, checkout public DS Bot at a fixed commit; no persisted Git credentials.
2. Verify exact commit, upstream version, `LICENSE`, `NOTICE` and `package-lock.json`.
3. Try `npm ci --ignore-scripts` and install DeepSeek Harness mock test dependencies with `--ignore-scripts` and pinned versions. Execute upstream `npm test` and shipped client build check. These steps genuinely test third-party package installation and mock tests **if they pass**, not real Bot-to-Bot LLM exchange.
4. In separate job, run VNext's existing offline handoff tests and CLI over a synthetic JSON generated at run time; assert `status=HOLD`, `production_recommendations=DISABLED`, 0 certified samples, no verified positive EV, and no note-text echo.

This workflow is triggered by this draft PR's changes only; it is not a scheduled market API collector or permanent DS Bot service. GitHub hosted runner has outbound npm access for package downloads, but gets **no model-provider or bookmaker secrets**. No Bot is granted GitHub write, no production file is mounted/written, and no untrusted notes become model inputs. Never copy personal API credentials into job logs.

## Limits / governance

- Upstream npm dependencies and test sources are third-party code; SHA pin and ephemeral runner reduce supply-chain drift but do **not prove absence of vulnerabilities**.
- The runner does **not** boot a persistent DS Bot, authenticate model providers, run real multiple Bot messages, test actual data permissions, or connect to the user's phone.
- A successful smoke is engineering compatibility evidence, **not** independent model/source provenance, licensed bookmaker odds, genuine forward validation, accuracy lift, positive EV, or betting qualification.
- PR #471 is still Draft and must be independently reviewed before any promotion. Issue #439 remains blocker until actual main protection and required independent reviews are enforced. This stacked PR must also remain Draft: do **not** merge/deploy until governance and functional risk gates are met.
- Original A/B/C, sealed V4.1, live system, production/settlement gates, frontend and data collectors remain untouched. **HOLD / DISABLED**.

## Acceptance evidence to record

For the exact stacked PR HEAD, inspect all GitHub check-runs and raw logs; enumerate skipped tests and any install failures separately, fix the defect rather than bypass the checks. Distinguish upstream mock CI from end-to-end real DS Bot runtime.
