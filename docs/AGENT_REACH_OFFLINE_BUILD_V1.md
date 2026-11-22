# Agent Reach phase 6 — Build-backend SHA-256 + container network-deny test

This is research-only in Draft PR #526, stacked on #525 → #524 → #523 → #522 → #521. It **must not** modify Football-King production workflows, markets, sealed predictions, HKJC content, odds quotas, data model inputs, EV or betting release guards.

## Security gap carried forward from phase 5

Phase 5 verified 13 independent, externally distributed *runtime* wheels by committed SHA-256. However `pip install --no-deps ./vendor/agent-reach` still launched isolated PEP 517 build dependency resolution. Agent Reach v1.6.1 declares `[build-system] requires=["hatchling"]` and `build-backend="hatchling.build"`; those build-backend packages were not hash pinned.

## Phase 6 evidence and enforcement

- **Git source:** upstream `Panniantong/Agent-Reach` exact revision `7a38047acf26a729cbb27851e3cb81639da86b29`, not a moving tag.
- **Candidate discovery:** [Actions 45027977803](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45027977803) downloaded `hatchling==1.27.0` plus build wheels (`packaging`, `pathspec`, `pluggy`, `trove-classifiers`) on Python 3.12 / Ubuntu 24.04 and generated untrusted *candidate* file hashes. A candidate is not an approval.
- **Independent Git commit:** `docs/agent_reach_build_wheelhash_lock.json` was committed **after** the candidate run. Exact versions are separately saved in `docs/agent_reach_build_wheels.txt`.
- **Later acceptance run:** `.github/workflows/agent-reach-offline-build-ci.yml` re-downloads each wheel and must match the **already committed** filename + SHA-256 exactly. Any extra/missing bytes fail CLOSED.
- **Second check:** inside Docker, pip must install these five distributions using `--require-hashes --no-index --no-deps` from *only* the prevalidated read-only wheelhouse, into a fresh venv.
- **No-network build:** Docker command uses `--network none`, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, limited CPU/memory/pids, an ephemeral writable tmpfs, and read-only mounts for the wheelhouse and upstream source. `pip wheel --no-build-isolation --no-index --no-deps` must successfully build Agent Reach from the pinned Git checkout with no outbound network. A separate in-container socket connectivity probe must fail to connect.
- **No collection:** this workflow NEVER executes Agent Reach `github read`. A prior manual smoke detected `RATE_LIMITED`, so automated reads remain disabled. There are no cookies, personal GitHub credentials, licensed racing feeds, sportsbook APIs, or bet execution.

All successful outputs remain **`HOLD / DISABLED`**. A passing build-guard test is not an active betting release.

## Precise limitations

**Wheel SHA match ≠ trust in original publisher.** The locked wheel bytes are identical to the ones previously downloaded, but no publisher signature, independent build reproducibility check, or review of every wheel's code has happened.

**Docker with --network none restricts the container**, not the *GitHub-hosted runner* itself: the runner downloads wheels and an image using its own outbound network before the container starts. The `python:3.12-slim` Docker image is currently a **mutable tag, not an immutable image digest**; container-layer supply chain must be pinned separately before stronger assurance. Docker resource restrictions are not independent evidence of a hardened production server.

This phase builds the upstream wheel but does **not** yet use that wheel as an input to an official football source. Real-world source identity, timestamp attestation, license, official HKJC data permissions, EV, prospective A/B results and a human code review are all unverified.

## Acceptance and rollout gates

1. GitHub exact-head isolated build workflow passes synthetic negative tests, committed SHA gate, pip hash gate, fixed source checkout, no-network wheel creation and network denial probe.
2. Full Football-King regression and repository safety workflows remain passing.
3. No auto-merge: Draft PR and independent code review required before moving upstream stages into `main`.
4. Future research: pin Docker image by digest, verify artifacts and signatures where available, implement a restricted allowlisted egress collection runner separately, then study legally licensed official football data. Do not use HKJC data without authorization.
