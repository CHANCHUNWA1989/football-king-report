# Agent Reach Phase 8 — Zero-direct-egress research collector boundary

This is a standalone security research increment stacked on PR #534 (and #526 → #525 → #524 → #523 → #522 → #521). The repository's live models, predictions, evidence archives, racing feeds, market quotas and betting guard are NOT changed.

## Threat and previous gap

Phase 7 proved a pinned Agent Reach v1.6.1 wheel can be built with `docker --network none`. That tests a *builder* only, not an eventual *collector*. A new research collector must not be allowed to open arbitrary outbound sockets, ignore domain policy, or turn untrusted external text into instructions. A Python-only URL whitelist is NOT an outbound network firewall.

## Single concrete acceptance goal

**Demonstrate a collector process in an isolated Docker network namespace with no direct Internet route, while exchanging one strictly bounded synthetic record via a local Unix domain socket.** No real football or HKJC public source has been approved, and no remote collection is attempted.

The new end-to-end CI:

1. Pulls the **already committed Docker digest** from `docs/agent_reach_builder_image_lock.json` on `linux/amd64`. Does not trust the moving `python:3.12-slim` tag.
2. Executes 11 synthetic positive/negative broker tests, plus existing builder-image contract tests. The tests cover request tampering, source spoofing, misrepresented external timestamps, forged remote execution, oversize payloads, prompt injection text, symlink/path collision and a fail-closed egress-open condition.
3. Starts a host-side **local-only** `AF_UNIX` broker with a fixed one-request protocol `GET SYNTHETIC_RESEARCH_V1` and a hardcoded synthetic body. It contains **no HTTP/HTTPS fetching, DNS resolution, browser access, accounts, cookies, API tokens or licensed content**.
4. Runs a Python research collector in Docker with `--network none`, `--read-only`, `--cap-drop ALL`, `no-new-privileges`, a nonroot UID, bounded CPU/RAM/pids and read-only mounts of the broker directory and client code. Direct numeric IPv4 and IPv6 TCP probes **must fail**, then the collector can receive exactly one synthetic record over the mounted Unix socket.
5. The collector checks the exact synthetic-only response schema, refuses a forged `origin_authorized=true` or `remote_request_executed=true`, and outputs a SHA256 of the synthetic body **without printing or retaining the raw text**. It always emits `status=HOLD`, `production_recommendations=DISABLED`, `eligible_for_model=false`, `verified_positive_ev=null`.
6. The host broker shuts down after one request and never operates as a general-purpose proxy. No data is stored in the repository or published as model signals.

## Strict limits

- This proves only the **container's direct network isolation and local synthetic ingress** on the GitHub-hosted test runner. It does **not** establish an outbound firewall on the runner host, or that remote domain allowlisting is enforced by a kernel-level policy for a connected collector. The host is still network-capable.
- The broker only serves a synthetic hardcoded fixture, **not a real sports source**. This test is not a claim that Agent Reach successfully fetched official football news, HKJC data, match lineups, actual odds, xG, scores or positive EV.
- The previous Agent Reach public GitHub API smoke was rate-limited. This stage does not retry, change accounts, proxy around quotas or hit any provider.
- Publisher attribution, timestamps, terms of service, licensed reuse, fixture/horse ID cross-validation and independent review remain pending. **There are zero approved live external domains.** A live egress broker would require a *separate* rights audit, strict target+DNS+TLS validation, redirect controls, firewall policy, request budgets and another PR.
- The pinned Docker image digest prevents builder/collector image tag drift, but alone does not prove a publisher signature, a vulnerability-free image, or host-level egress hardening.
- Do not merge without independent Code Review and green repository safety CI. `HOLD/DISABLED` must remain unchanged.

## Exit criteria

- Exact-head GitHub Actions succeeds in all unit tests and the real Docker `--network none` + mounted Unix socket experiment.
- Host-side broker serves exactly one synthetic request, doesn't have any external fetch implementation.
- Any attempt at direct network access, arbitrary URL, forged source status, altered schema, raw content escape or model promotion fails or remains HOLD.
- Full Football-King regression/safety checks remain green; PR stays Draft pending independent review.

**Next stage:** A legal/source-rights review for a narrowly selected football official publisher and a separate proxy with *actual* enforced destination filtering; test with a dedicated collection runner and independently logged outbound request telemetry, without connecting it to betting models. Do not give the remote broker live network access before those gates.
