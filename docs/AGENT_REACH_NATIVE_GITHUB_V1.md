# Agent Reach Phase 2 — Strict native GitHub envelope import

**Scope:** This small, stacked research PR imports a native Agent Reach 1.6 JSON result from one specified *public* GitHub repository and hands it to the existing V1 quarantine module. It does not fetch any network data itself. It never imports an authenticated login session, calls a bookmaker/HKJC service, runs a predictive model, or publishes raw text.

## Source audited

- Upstream project: Panniantong/Agent-Reach (v1.6.1 project metadata checked on 2026-11-22).
- Native CLI contract: schema_version=1, ok, channel, action, backend, items, error (agent_reach/runtime/result.py).
- Channel specific backend: github-api, explicitly selected with --backend github-api (agent_reach/channels/github.py).
- One normal Github repository read yields one item with URL, title, text. The item published_at field can mean repository creation time, **not** publication of current README content. Accordingly, we always set published_utc=null.
- The exact upstream version is not cryptographically pinned by this importer. The envelope can be fabricated; parsing it does not prove a CLI ran.

## One-repo, anonymous manual capture (NOT run by CI)

After dependency/supply-chain/security review, use an isolated machine with no GitHub login, access token, browser cookies or reusable home directory. Set outbound firewall rules to permitted public destinations and disable other channels. Where allowed by terms, the operator may run:

    agent-reach github read Panniantong/Agent-Reach --backend github-api --timeout 15

Save that single JSON result to a private, local temporary path. Do NOT commit it to this public repository: the result may include text, upstream metadata, or incidentally embedded sensitive data. If the CLI has not been installed, this phase is still usable with **synthetic** JSON for tests, but no genuine source acquisition is established.

Then, locally:

    python ops/agent_reach_native_github.py --repo Panniantong/Agent-Reach --native-json /tmp/reach-native.json --output /tmp/reach-quarantine.json --captured-utc 2026-11-22T11:55:00Z --now-utc 2026-11-22T12:00:00Z

The timestamps above are illustrative, are caller-supplied and are **not attested**. Use actual UTC timestamps at run time.

The importer validates source title and canonical URL, rejects mismatched repositories, query strings, credentials, unknown backends, failed native responses, multiple results, missing body, overly large inputs, and wrong capture chronology. It retains no raw text; only quarantined metadata and a local hash.

## What this does NOT establish

- It does not install or execute Agent Reach, so agent_reach_executed remains false.
- GitHub API read-only access is not independent evidence of a sports result, lineup, official injury, match event identity, or source publishing time.
- One host match is not proof of trusted upstream network transport, URL redirection safety or the provenance of arbitrary contents. An actual runner will require its own sandbox/firewall and release pin.
- No HKJC access or permitted reuse, no bookmaker executable quotes, no positive EV, no model accuracy improvement, no model eligibility, no signed time witness.
- Formal prediction and betting status remains HOLD / DISABLED.

## Tests and next acceptance gate

    python -m compileall -q ops
    python -m unittest discover -s ops/tests -q

The separate GitHub Actions job runs focused **synthetic** native-format tests, no network or secrets. Exact-head CI and independent review remain required. Because this is a **stacked** PR, first review/merge the V1 quarantine PR #521; only then retarget/review this phase for main. Do not auto-merge either stage.

**Next gate:** pinned Agent Reach release and dependency review; a distinct private ephemeral runner with effective egress filtering; actual anonymous, license-compliant Github read; signed acquisition receipt and observed network log; on failure return HOLD without retries or fallback. Only then consider expansion into football club announcements and legally licensed Hong Kong racing feeds.
