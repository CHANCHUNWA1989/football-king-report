# Agent Reach Phase 4 — Isolated install and fixed dependency-version audit

This is a **limited supply-chain hardening** experiment, stacked on the public GitHub live smoke PR #523, which depends on #522 and #521. It does not change the football models, historical data, betting status, quotas, or any HKJC source. It does not create automated scheduled collection.

## Actual problem reproduced

The previous public smoke runner used:
`python -m pip install --no-cache-dir ./vendor/agent-reach`

Even though the Agent Reach upstream source commit was pinned, its `requests>=2.28`, `loguru>=0.7`, `pyyaml>=6.0` and indirect dependencies were not version-pinned. Fresh installs could silently select newer releases and alter behavior. All package versions in `docs/agent_reach_smoke_constraints.txt` were observed in the **successful** 2026-11-22 GitHub Actions run 45022712495. They are not guessed package versions.

## Changes and acceptance

The dedicated live smoke job now:

1. Checks out exact upstream commit `7a38047acf26a729cbb27851e3cb81639da86b29` as before.
2. Creates a temporary, isolated Python venv under `$RUNNER_TEMP/reach-venv`.
3. Installs the local upstream source using pip constraints fixing **14 observed runtime distribution versions**; any unsatisfiable exact pins must fail the job instead of silently resolving to newer versions.
4. Runs `pip check`.
5. Runs `ops/agent_reach_dependency_guard.py` against the constraints file and the *actually installed* distribution versions; any missing/extra/loose line in the constraints inventory, missing installed package or version mismatch blocks the public read.
6. Executes the same one public anonymous `github-api` read using only the fresh venv binary. Its subprocess still receives a new HOME and a minimal environment.
7. Saves only the existing sanitized short receipt; no raw provider responses or tokens.

The added tests are synthetic, offline, and negative-heavy: exact pins, missing packages, version drift, modified inventory, duplicate/loose/editable requirements, no raw secrets in errors, and continued HOLD/DISABLED behavior. Full repository CI and independent review are still required.

## What is NOT solved

**Version pinning is NOT cryptographic artifact locking.** Wheel SHA-256 hashes have not been pinned, and pip's isolated build-system dependencies are not fully hash-locked. Python venv isolation is not OS/container security isolation. GitHub-hosted runner egress is not restricted by a firewall, and GitHub Actions upload artifacts are not automatically external time attestations. Upstream release SHA is a Git commit verification only.

This means the stage may legitimately pass as `PASS_VERSION_ONLY` while `supply_chain_hash_verified=false`, `build_isolation_hash_verified=false`, `egress_firewall_verified=false`, `eligible_for_model=false`, `production_recommendations=DISABLED`.

Next required security step: hash-verified wheelhouse plus an independently restricted network execution environment, then independent human PR review. Only after both may a separate study assess *licensed* football official news and Hong Kong racing sources. Official source identity and publication time still cannot be inferred from ordinary Agent Reach metadata.

**Stacked order:** PR #521 -> #522 -> #523 -> this PR. Do not merge or deploy these unreviewed research changes directly to main.
