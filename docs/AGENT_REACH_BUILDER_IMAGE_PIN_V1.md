# Agent Reach Phase 7 — Immutable Docker builder image identity

**Research-only, stacked PR #534** on #526 → #525 → #524 → #523 → #522 → #521. This change is restricted to the **builder image immutability**, not new sports data or production code.

## Reproduced security issue

The phase-6 offline build executed `docker run ... python:3.12-slim`. This tag can point to a different image on a later date, even though 5 Hatchling build wheels and the upstream Agent Reach Git source are separately pinned. `--network none` prevents normal outbound connections from the container, but does not prevent a drifted base image from being pulled on the GitHub runner beforehand.

## Evidence and approval trail

1. [Candidate discovery Actions #45117541781](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45117541781) pulled the public `docker.io/library/python:3.12-slim` tag explicitly on `linux/amd64`, read its `RepoDigests`, and recorded a candidate manifest SHA-256 digest. This run's tag-based pull was **discovery only**.
2. On a **subsequent, separate commit**, the observed digest was saved as `docs/agent_reach_builder_image_lock.json`. This manifest contains only `schema`, `repository`, `observed_tag`, `platform`, `digest`; the digest is of the registry's image manifest/index, not the local Python package's SHA-256.
3. The new guard `ops/agent_reach_builder_image_guard.py` rejects non-approved registry names, moving tags, platform drift, invalid SHA-256 digests, unexpected fields, symlinks and excessively large lock files. Its acceptance report still keeps `HOLD/DISABLED`; it does not claim that parsing proves the image download.
4. On the separate acceptance run, CI **must pull by exact `docker.io/library/python@sha256:...` reference**, verify `linux/amd64`, then run `docker --pull never --platform linux/amd64 --network none` on that image. The prior five build-wheel SHA-256 controls, pinned Agent Reach Git source commit, read-only mounts, resource limits and network-denial test are preserved.
5. The candidate-discovery workflow is manual-only after committing the lock. CI does not call Agent Reach public GitHub API (prior `RATE_LIMITED` remains respected), source feeds, HKJC or bookmaker APIs.

## Approval evidence on top of pinned builder image

A separate review-evidence advisory was added to the stacked research base. A pair
of GitHub PR metadata API reads (one **before** and another **after** reading reviews)
is now checked against the immutable `pull_request` event head SHA and PR number.
A mismatch must result in HOLD, and zero independent non-author reviews also
results in HOLD. This checks metadata consistency **only**; the GitHub repository
administrator must still enforce a trusted default-branch ruleset and required
approvals. A Docker image SHA-256 digest is not a security review approval.

If the job is `skipped` while this PR is Draft, this is deliberate; its
readiness status must not be considered approved or safe to merge. All other
builder-specific CI checks remain required. See
`docs/AGENT_REACH_REVIEW_EVIDENCE_V1.md` and issue #539.

## Precise limitations and non-claims

- An image digest fixes **bytes served at that registry address**, subject to Docker's digest verification. It does **not** prove Docker publisher signatures, provenance, supply-chain audit, full CVE-free security, or independent reproducible builds.
- The image manifest may support multiple architectures; this workflow additionally locks the runner to `linux/amd64`.
- `--network none` is only a container-network restriction for **this builder**, NOT a host-level firewall or a permission-controlled collection runner. The GitHub-hosted runner itself needs outbound network for public checkout and wheel/image downloads.
- This change does not authorize arbitrary Agent Reach web collection. No licensed real-time football/HKJC feeds, bookmaker prices, match identity witnesses, authenticated publisher time or model evidence have been obtained.
- All formal `production_recommendations=DISABLED`, `status=HOLD`, `eligible_for_model=false` and `verified_positive_ev=null` restrictions remain; testing installation integrity cannot establish prediction accuracy.

## Acceptance gate

Require the exact-head new image guard tests, exact pinned image Docker pull, image architecture check, successful Git-pinned Agent Reach wheel build offline, failed network probe, and all relevant Football-King safety regression Actions. Independently review before any merge. If any source or lock check fails, **fail closed** without falling back to the floating tag.

**Next separate research stage:** review approved official football source-domain allowlist and public redistribution terms, then validate a distinct actual collection runner behind an enforceable restricted-egress environment; no HKJC access until separate authorization. Do not mistake an allowlist in Python for network enforcement.
