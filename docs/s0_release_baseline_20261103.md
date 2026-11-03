# 足球王者 S0｜真實公開站點 + GitHub 基準核對（2026-11-03）

## 本次核實到的實際狀態

- Public iPhone site: https://chanchunwa1989.github.io/football-king-report/
- Latest captured website `status.json`: `checked_utc=2026-11-03T02:24:44.490908+00:00`, `status=RESEARCH_ONLY`; all 6/6 current public fixture sources responded; `production_recommendations=DISABLED`.
- Same timestamp `quality.json`: 165 public matches, **21 precise-kickoff**, **18 initially eligible pre-match snapshots**, 0 critical quality errors. Warnings include unknown upstream publication time, many missing verified kickoff hours, and only a subset of leagues with independent source cross-check. **18 is not independently qualified forward evidence**.
- `production_gate.json`: 73 **legacy / unverified** research-settlement records; independently authenticated forward samples **0**, authenticated week blocks **0**, qualifying leagues **0**. `HOLD` and all 9 listed release conditions false; authenticated forward-admission not implemented.
- GitHub main: `848eedb112cd26a850df23a7a9a90cf84129f706`, updated 2026-11-03 03:29:08 UTC by the archival bot; the GitHub branch metadata returns `protected=false`. Dedicated branch-protection API was unavailable to the connected app (403), so no enforced ruleset has been independently verified.
- Observed open PRs on 2026-11-03: #362 and #364 (non-draft), #380, #381, #382 (Draft). These were observed individually, **not a complete assertion that no other open PRs exist**.
- `market/collection_status.json` captured `as_of_utc=2026-11-03T01:59:39.431777+00:00`: `RESEARCH_ONLY`, free quota last reported 456 remaining / 44 used, `DISABLED`. This is vendor history/derived research only, not a verified executable betting price.
- `sources/seven_quality_gates_latest.json`, captured 2026-11-02 04:20 UTC: **1 PASS, 5 PARTIAL, 1 HOLD** and `can_recommend_bets=false`. Counts can change and are not a future guarantee.

All sources above were fetched as read-only public GitHub metadata or deployed public site JSON. The website endpoints returned HTTP 200. Source publication timestamps and independently authenticated identity are **not** guaranteed by an HTTP 200 response.

## Concrete addition in this S0 PR

`python ops/release_baseline.py`

- Public, read-only: uses **exact preapproved HTTPS endpoints only**, no secrets, no private API, no trading, no live market-billing calls.
- Retrieves current main SHA / protected flag, **first 100 open PRs (refuses a full potentially truncated page)**, deployed `status.json`, `quality.json`, `production_gate.json`. Captures exact as-of site timestamp, freshness, source coverage, legacy vs authenticated samples.
- Fails closed if missing/ambiguous UTC, inconsistent timestamps, impossible coverage, duplicate JSON keys, invalid SHA or PR identity, oversized response, HTTP redirect, suspicious future site timestamps.
- `BASELINE_CAPTURED` means all public documents were retrieved and internally consistent; it **does not mean S0 fully approved or the system releasable**. `SITE_STALE`, `AUDIT_ALERT`, or `AUDIT_INCOMPLETE` reject acceptance.
- Always prints `ready_for_release_b=false`, `verified_positive_ev=false`, `permission_to_trade=false`, `production_recommendations=DISABLED`. Site claims are recorded separately from authenticated evidence.
- CLI can write `--output <path>` using exclusive creation, never overwrites an existing report. Output may include public PR metadata, not personal accounts or private research data. Keep audit output under controlled project storage; **do not** put mutable snapshots into the code `main` branch.
- Offline regression tests use synthetic injected snapshots only; they do not contact GitHub or consume API quotas.

## Next prerequisites to complete S0 and enter S1

1. Reproduce this public baseline on an approved live runner; compare timestamps, PR count, site health and main SHA, then retain a pinned audit report. **This PR's offline tests do not prove a live run**.
2. Reconcile complete main workflow writer/reader inventory from [PR #381](https://github.com/CHANCHUNWA1989/football-king-report/pull/381) and [PR #382](https://github.com/CHANCHUNWA1989/football-king-report/pull/382), including scripts and workflows beyond static matches. Update Issue #383 with every unresolved writer and rollback path.
3. Obtain a **separate, authorized independent reviewer** to inspect #362/#364/#380/#381/#382 and this S0 report. A review comment under the original author's identity is **not** independent approval.
4. Do not merge PRs or activate protected-main requirements while archival workflows still write directly to main. Independent main ruleset enforcement must be verified separately.
5. Do not promote qualified data, odds EV, ROI, or independent forward samples on the basis of automated tests or source counts.

**S0 only fixes baseline reproducibility.** All original betting safety gates stay unchanged, and all model weights / archived predictions remain intact.

Tracking: [Master #383](https://github.com/CHANCHUNWA1989/football-king-report/issues/383), [Release blocker #56](https://github.com/CHANCHUNWA1989/football-king-report/issues/56).
