# Agent Reach Phase 3 — Pinned anonymous public GitHub smoke (research only)

**Date:** 2026-11-22 Hong Kong time. **Stacked on PR #522**, itself stacked on #521.

## Exact scope

This phase is intended to prove whether an *actual* `agent-reach github read` subprocess can read **one public repository only** in an ephemeral GitHub Actions job. It is not a football match collection, an HKJC feed, an odds feed, a model run, or a live recommendation. No cron, daily deployment, changes to odds quotas, or formal forecast promotion.

The external release source is pinned to **Panniantong/Agent-Reach v1.6.1 commit `7a38047acf26a729cbb27851e3cb81639da86b29`**. Checkout verifies the exact 40-character SHA before use. Installer resolves upstream requirements such as yt-dlp and requests; **transitive dependencies are not yet hash locked**, so this is limited to a temporary, read-only, no-user-secrets CI environment. Checking the commit does *not* mean complete supply-chain audit or continuous egress restriction.

The only permitted command is:

    agent-reach github read Panniantong/Agent-Reach --backend github-api --timeout 15

The Python runner always selects this argv itself; no arbitrary command strings. It checks the upstream checkout commit, CLI version, exit code, native JSON version, `github-api` backend claim, one matching repository URL/title, and the output size. It creates a fresh HOME with no source browser sessions, passes a minimal subprocess environment without GH_TOKEN/GITHUB_TOKEN or cloud credentials, and never calls setup/login/add/remove/update. Upstream GitHub channel is explicitly restricted to public github-api backend. It **does not enforce a kernel or firewall egress allowlist**: only the requested CLI action is limited. A more isolated network layer is required before exposing business or private information.

The runner records its own start/end UTC wall-clock observations and a digest of the native bytes. These are **not external timestamp attestation**, and hashes **do not prove upstream source truth**. No raw README/JSON, browser cookie, secret, bookmaker quote, or HKJC text is uploaded. The only artifact is a short sanitized receipt, retained 7 days. The artifact may not exist if checkout or installation fails.

## Hard safety boundaries

- `status=HOLD`, `production_recommendations=DISABLED`, `eligible_for_model=false`.
- `verified_positive_ev=null`; the run must never emit staking.
- A CLI read can be observed while remaining **unattested**, `agent_reach_execution_independently_verified=false`.
- Read-only public GitHub succeeds only if external vendor responds. A job passes only if actual native JSON was parsed; no mocks or synthetic output are accepted in the live job.
- If the process fails, times out, schema mismatches or the wrong URL is returned, save a `HOLD` receipt with sanitized reason and fail the job. Synthetic tests are performed in a different job and cannot substitute for a real run.
- This research workflow has no schedule and is only triggered for proposed changes / manual dispatch when available. It does not touch production workflows, existing archives, model code, market sources, licensed data, or the release guard.

## Acceptance

1. GitHub Actions `no-network-tests` passes both prior adapters plus the live-runner synthetic contracts.
2. `actual-public-read` records a genuine process exit 0, native schema 1, backend github-api and same public source URL/title.
3. Archive shows `capture_status=PUBLIC_READ_OBSERVED_UNATTESTED`, never certified sports data or a model signal.
4. All affected repository safety CI remains green. Independent reviewer required before merging #521, then #522, then this stacked PR. Never bypass pending human review because CI is green.

**Remaining blockers:** Source dependency lockfile/hash audit, dedicated firewall-restricted runner, formal source and time attestation, legal licensing for third-party football/HKJC datasets, independently verified fixture/horse identities, shadow model evaluation, and credible positive EV evidence. Until then, both sports systems stay `HOLD / DISABLED`.
