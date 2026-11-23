# Agent Reach phase 5: external runtime wheel SHA-256 integrity gate

This increment is a **research-only integrity check**, not full end-to-end supply-chain trust. It is stacked on PR #524, which is stacked on #523/#522/#521. No changes to existing football models, markets, releases, site publishing, forecast seals, Hong Kong racing data, or wagering status.

## Evidence trail and no-self-certification rule

1. On 2026-11-22, [candidate-discovery workflow 45023935890](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45023935890) ran on a clean GitHub-hosted Ubuntu 24.04 Python 3.12 runner. It fetched **13 public external runtime distribution wheels**, each fixed to a version already observed in a successful Agent Reach v1.6.1 smoke. Its first CI failed because the strict wheel filename validator omitted hyphens; the guard was fixed and tests rerun. That run produced a candidate wheel list with file names and SHA-256 hashes. This discovery job is *not* proof of source legitimacy.
2. The list was copied as a **committed file** in `docs/agent_reach_wheelhash_lock.json` in a later Git commit. That avoids generating and accepting hashes on the same installation run.
3. Subsequent Actions now download fresh wheel bytes, compare the full **filename + distribution + version + count + SHA-256** to the committed manifest, then generate a requirements list with `--hash=sha256:<digest>` for pip to verify again under `--require-hashes --no-index --no-deps`.
4. If any filename, missing/extra package, byte change or symlink is observed, the job exits nonzero before the wheel installation and before any Agent Reach CLI network request.
5. The exact upstream Agent Reach source remains fixed to `7a38047acf26a729cbb27851e3cb81639da86b29`, but its local packaging/build backend is still not hash-locked.

All tests in `ops/tests/test_agent_reach_wheelhouse_guard.py` use synthetic wheel files; only a separate live job actually downloads PyPI wheels and performs the limited anonymous `github-api` public repository read.

## Assumptions and restrictions

- **Platform-specific artifact lock**, not a multi-platform lock: GitHub runner Ubuntu 24.04 x86_64, Python 3.12. Different architectures or future artifacts legitimately fail until a new independently audited manifest is approved.
- A matching hash establishes *identity to these committed downloaded bytes*, not that PyPI originally served safe code, that a maintainer is trustworthy, or that a publisher's signature was verified.
- Only 13 **external runtime wheels** are locked. The source package `agent-reach==1.6.1` is pinned by Git commit separately. Hatchling and related pip isolated-build dependencies are **not** included in this wheelhash manifest. Do not claim a fully hash-locked supply chain.
- The temporary Python venv avoids mixing distribution versions with the main runner but is **not** a kernel/container security boundary.
- No egress firewall is present: this test cannot claim that arbitrary subprocess network access is blocked. No cookies, personal login or bookmaker keys are provided intentionally.
- The only successful output is public GitHub read observation with **QUARANTINE / HOLD**, not independently attested sports evidence. It cannot prove the source's publication time, licensed redistribution permission, calibration improvement, executable market prices or positive EV.

## Acceptance

Run the five focused suites (quarantine, native GitHub envelope, pinned public smoke, dependency guard, wheelhouse guard) plus all repository safety CI. For the live job, require SHA-256 manifest gate followed by pip hash check, 14/14 installed distribution-version confirmation, and actual public read success. The same-source fake or changed wheel test must fail closed.

**Unresolved gates:** cryptographically locked build dependencies/source wheel, upstream signature review, restricted egress environment, independent code reviewer, public football data terms/permissions, HKJC dataset licensing, independent fixture and horse IDs, real data point-in-time attestation, prospective challenger validation. All research remains `production_recommendations=DISABLED`. Do not merge without independent review.

## Real CI acceptance and public API rate-limit handling (2026-11-22)

[Real hash-locked install run 45024068467](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45024068467) **passed the 13/13 external wheel SHA-256 gate against the previously committed manifest**, pip's `--require-hashes --no-index --no-deps` second gate, `pip check`, and 14 installed distribution-version checks. However its *additional* public GitHub read failed with native CLI error **`RATE_LIMITED`**, correctly recorded as `HOLD` and exit 2. This job as a whole was **not successful**. Do not call this a successful live-read run or hide the rate limit. It is evidence of both successful runtime-wheel checks and a separately blocked public API request.

To comply with Agent Reach's own rate-limit policy, PR-triggered runs now perform wheel verification and the offline install/version audit only. The public `github read` step is **skipped on PR events**, and remains explicitly manual via `workflow_dispatch` in a later, rate-limit-permitted context. No automatic retries, backend hopping, token switching or account circumvention. The next CI passing on PR thus confirms package integrity only, **not** fresh public GitHub access.

The historical source-signed acquisition, wheel build toolchain signatures, host network egress firewall, source licensing for both sports and independent human review remain outstanding.
