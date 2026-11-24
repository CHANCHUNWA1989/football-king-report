# GitHub football analytics integration review — 2026-11-15

**Native Kloppy 3.19.1 real-wheel run succeeded later on 2026-11-15. See §9 for exact evidence and limits; earlier 'not run' statements are historical.**

Scope: compare publicly available upstream source, **software** licenses,
maintenance, dependency cost, fit with Football King VNext, and deliver a
first **offline-only, research-only** Kloppy event normalization seam.

**No upstream source was copied into this repository.** This document does
not grant the right to scrape, train on, republish, or sell third-party match
events, lineups, tracking data, or bookmaker prices. No external data was
downloaded during this integration. Upstream API smoke testing with an actual
installed Kloppy wheel and lawfully obtained event fixture is **not yet done**.

## 1. Source-checked candidates

Verified 2026-11-15 against upstream GitHub REST metadata, LICENSE/LICENCE and
project metadata (re-evaluate when packages change):

| Project and upstream | License evidence | Last identified release | Snapshot indicators | Fit / decision |
| --- | --- | --- | --- | --- |
| [martineastwood/penaltyblog](https://github.com/martineastwood/penaltyblog) | [LICENCE](https://github.com/martineastwood/penaltyblog/blob/master/LICENCE), MIT, 2021 Martin Eastwood | [v1.13.1](https://github.com/martineastwood/penaltyblog/releases/tag/v1.13.1), 2026-10-05; master commit `6870f0e762e9cba35fa722dc14a8daeaf8bc6134` | 250 stars; last default-branch commit 2026-10-19 | **Best direct outcome-model fit** (Poisson, Dixon-Coles, bivariate models). Already implemented as optional offline research bridge in unmerged Draft PR #458. Do NOT clone/copy a second implementation. |
| [probberechts/soccerdata](https://github.com/probberechts/soccerdata) | [LICENSE.rst](https://github.com/probberechts/soccerdata/blob/master/LICENSE.rst), Apache-2.0, with embedded footballdata MIT notice; [pyproject.toml](https://github.com/probberechts/soccerdata/blob/master/pyproject.toml) confirms Apache-2.0 | [v2026.43.0](https://github.com/probberechts/soccerdata/releases/tag/v2026.43.0), 2026-10-19; mainline commit `b507432742119ba3897533895c92ac3a4f2b9259` | 2141 stars; last observed default-branch commit 2026-10-18 | Historic data **scraping** adapter, not a model. Already optional in Draft #458. GitHub's aggregate license API returned NOASSERTION; actual LICENSE.rst and package metadata support Apache-2.0. Third-party data rights remain unverified. |
| [ML-KULeuven/socceraction](https://github.com/ML-KULeuven/socceraction) | [LICENSE.rst](https://github.com/ML-KULeuven/socceraction/blob/master/LICENSE.rst), MIT, KU Leuven | [v1.5.3](https://github.com/ML-KULeuven/socceraction/releases/tag/v1.5.3), 2024-08-15; master commit `93a1242d46c104889205753accaabadb00c45c6d` | 830 stars; most recent default-branch commit 2026-01-07; Python constraint in published pyproject: `>=3.9,<3.13` | Valuable **later** for event-based xT/VAEP once licensed event feeds, attribution, timestamping and model/OOS validation exist. No direct proof of improved 1X2, Asian handicap, totals or EV. |
| [PySport/kloppy](https://github.com/PySport/kloppy) | [LICENSE](https://github.com/PySport/kloppy/blob/master/LICENSE), BSD-3-Clause, 2020 PySport | [v3.19.1](https://github.com/PySport/kloppy/releases/tag/v3.19.1), 2026-10-03; master commit `a9651eba7c4dbbe2d2fc6d4cffb4aea63fadac11` | 572 stars; most recent default-branch commit 2026-11-06; Python >=3.9 per pyproject | **Chosen incremental seam:** offline event/tracking *format normalization*, not a prediction engine. Supports future socceraction pipeline without duplicating existing penaltyblog model. |

Stars, commit recency and release recency indicate ecosystem visibility, not
correctness or demonstrated prediction accuracy. The listed commit SHAs are
default-branch snapshots, **not immutable package/hash attestations**.

## 2. Why Kloppy is the next integration, not a second Penaltyblog

The VNext unmerged [Draft #458](https://github.com/CHANCHUNWA1989/football-king-report/pull/458)
already contains optional `ops/penaltyblog_research_bridge.py`, an optional
`soccerdata.MatchHistory` bridge, extensive offline/chronological diagnostics
and an earlier open-source review. Replicating those endpoints would create
two inconsistent forecast pipelines without independently verified outcomes.

Kloppy v3.19.1 documents the already-loaded `EventDataset.events`,
`EventDataset.metadata.game_id`, `metadata.teams` and `Event.event_id`,
`Event.event_name` and `Event.team.team_id` interface. References:

- https://kloppy.pysport.org/user-guide/loading-data/
- https://kloppy.pysport.org/reference/domain/models/event/event/
- https://kloppy.pysport.org/user-guide/concepts/metadata/

New `ops/optional_kloppy_event_research.py` accepts only a pre-loaded
EventDataset-like object plus a strict source manifest; it does **not** import
Kloppy, download match data, read files, or send HTTP requests. It verifies
**internal structural consistency only**: native match/team/event identity,
duplicate event IDs, a bounded event count, and the operator's claimed
event availability time strictly before the target research cutoff. It
computes descriptive pass/shot counts for two teams, ignoring other events.

No odds, scores, xG, predictions, calibrated strengths, model rankings,
EV, ROI, wager sizes, certified source rights, or independently witnessed
cutoffs are derived from those counts. The source rights URL is a **reference
provided by the operator, not an authenticated legal clearance**.

## 3. How to run locally after permission is independently reviewed

Only in an **isolated, nonproduction** research environment, after confirming
that the particular provider's event/tracking file is lawfully usable:

```python
# Optional external dependency, pinned/reviewed separately. Do NOT run
# this local loader on hosted CI or directly in production.
from kloppy import statsbomb
from ops.optional_kloppy_event_research import (
    SCHEMA, summarize_local_event_dataset,
)

dataset = statsbomb.load(
    event_data="/approved/local/events.json",
    lineup_data="/approved/local/lineups.json",
)
manifest = {
    "schema": SCHEMA,
    "source_namespace": "approved_source_name",
    "source_event_id": "provider-native-match-id",
    "rights_reference_url": "https://provider.example/actual-terms",
    "source_available_utc": "2026-10-01T12:00:00Z",
    "target_as_of_utc": "2026-11-01T12:00:00Z",
}
report = summarize_local_event_dataset(dataset, manifest)
assert report["production_recommendations"] == "DISABLED"
```

*The paths, provider and timestamps above are illustrative, NOT a tested
licensed match; the Python API call is documented upstream but this PR has
only run synthetic structural contract tests.* The operator must substitute
an actual authorized local file, true provider-native identifiers and real
timestamps, then separately obtain rights and source-origin verification.
Do not pass `http://`, `https://` or `s3://` URLs as loader inputs in
this workflow. No raw event data, private accounts, tokens, or proprietary
feeds should be uploaded into a public GitHub PR or CI artifact.

## 4. Release and license controls

1. Respect BSD-3-Clause terms if **copying** Kloppy source; retain copyright,
   license and disclaimer. This change has **no vendored upstream code**.
   If installing third-party packages later, inventory transitive licenses,
   version-lock and evaluate supply-chain integrity separately.
2. Program licensing is **not** an event-data license. Obtain explicit terms
   for the **specific upstream provider, competition, match, format, use,
   retention and redistribution** independently of the library.
3. Do not infer event `metadata.date` or local match clock as a verified UTC
   kickoff. The bridge deliberately has no `kickoff_utc` output.
4. A self-asserted `source_available_utc` and terms URL are not
   cryptographically witnessed source custody. The adapter always reports
   source/data rights, capture and native match identity **not independently
   authenticated**.
5. Preserve existing sealed A/B/C forecast archive; do not train, fit,
   publish to the site or release recommendations from this output.
6. Offline synthetic tests are **not a real Kloppy wheel smoke test**,
   independent OOS demonstration, validated betting market, or evidence of
   positive EV. Review actual version/API, rights, raw-file hashes and
   independent verifier before any stronger data path is proposed.
7. **Draft only, HOLD/DISABLED**. GitHub main protection and genuinely
   independent human review (Issue #439) are still blockers. Never merge,
   deploy or unblock bets based only on the CI passing.

## 5. Native wheel smoke rehearsal (prepared, not yet CI-verified)

`ops/tests/kloppy_native_real_smoke.py` is a runnable optional test against
**genuine Kloppy native** `EventDataset`, `Metadata`, `Team`, `PassEvent`,
`ShotEvent` and `GenericEvent` objects. Its inputs are fully manufactured
in memory; it neither reads a provider fixture nor starts a network fetch.
The test rejects a genuine `GenericEvent(event_name="shot")` being counted
as a typed shot. The production-neutral adapter now uses `event.event_type`
and checks that `event.event_name` matches the enumerated type.

Verify this in a sandboxed external runner with *no provider keys or data*:

```sh
python -m pip install --no-input --only-binary=:all: 'kloppy==3.19.1'
python -m unittest ops.tests.kloppy_native_real_smoke -v
python -m unittest ops.tests.test_optional_kloppy_event_research -v
```

**Execution status:** The latest normal repository GitHub CI verifies the
standard-library contract tests; it does not install Kloppy. Attempts to
register a separate pull-request workflow on this branch failed *before any
test job was instantiated*. The experimental workflow was deleted and the
required `football-king-ci.yml` restored byte-for-byte. **Do not claim the
native wheel smoke passed until the commands above run successfully on an
appropriately approved isolated runner, with verifiable job logs.**

A pinned *version number* is not a pinned package wheel hash or a locked
transitive dependency graph. Verify supply-chain hashes, dependency licenses,
and package provenance before expanding beyond a private smoke environment.
No software license establishes rights over provider event data.

## 6. Local wheel hash and provenance preflight — source-checked, not run with the official wheel

The official PyPI release page at
https://pypi.org/project/kloppy/3.19.1/ lists a built wheel
\`kloppy-3.19.1-py3-none-any.whl\` published on 2026-10-03 with
SHA-256:

\`\`\`
bdb468cc7b23a6c58276fdd8dbdb9c331e8cf4be8b721fdb97b7ec69d186b5ba
\`\`\`

PyPI reports trusted publishing and a GitHub Actions provenance attestation
for upstream publishing commit
\`11822569caa4490e99321be54afc3919ad6b417a\`, but this project's CI
has **not independently fetched, verified or signed** those attestations.

\`ops/kloppy_offline_wheel_preflight.py\` now checks the **existing local
file** against that hardcoded official SHA-256, its exact wheel name and
internal package metadata. It reads only local bytes and does not install or
execute third-party code. \`ops/tests/test_kloppy_offline_wheel_preflight.py\`
covers the fail-closed behavior with **manufactured archive files**, not the
actual PyPI release.

The following runbook applies **only after** an isolated wheel and its
runtime dependencies have been independently acquired and vetted:

\`\`\`sh
# 1. The operator must independently obtain this official PyPI wheel
#    into a local, access-controlled scratch directory. No URLs, keys,
#    data, or third-party sources are passed to the research adapter.
python -m ops.kloppy_offline_wheel_preflight \
  --wheel /approved/wheels/kloppy-3.19.1-py3-none-any.whl

# 2. Install into a disposable, offline environment that already contains
#    separately approved and pinned transitive dependencies. --no-deps
#    deliberately refuses to retrieve anything automatically.
python -m pip install --no-index --no-deps \
  /approved/wheels/kloppy-3.19.1-py3-none-any.whl

# 3. Run the two real native-object tests using fabricated event records.
python -m unittest ops.tests.kloppy_native_real_smoke -v
\`\`\`

**Do not run step 2 if independent dependency approval is unavailable.**
\`--no-deps\` guarantees neither dependency presence nor integrity; a wheel
hash check alone is not a complete software bill of materials or source code
review. If any preflight, dependency, native smoke or later licensed data
gate fails or is unavailable, retain **HOLD / DISABLED**. No installation
of third-party software is part of the default VNext safety CI.

**Recorded status at this review:** PyPI filename/hash/provenance claims
were inspected; the official 30.1 MB wheel could not be fetched in this
execution environment and \`kloppy\` is not installed, so **real-wheel hash
match and native-object smoke are NOT verified**. The local wheel checks
have only synthetic-test coverage. No licensed match event data is supplied.


## 7. Native record-to-dataset ownership (match isolation)

The Kloppy upstream implementation (tag v3.19.1) uses
\`Dataset.__post_init__\` to bind each \`DataRecord\` to the actual native
\`Dataset\` via \`record.set_refs(dataset=self)\`. See
https://github.com/PySport/kloppy/blob/v3.19.1/kloppy/domain/models/common.py.

The optional adapter now explicitly requires every record to contain a
native \`record.dataset\` reference **identical by object identity** to the
passed \`EventDataset\`. It rejects missing/foreign references, even if
the event ID, team ID or headline match metadata appear consistent. It
therefore requires a full native unfiltered EventDataset; records copied
from elsewhere or views whose records still reference an underlying dataset
are intentionally fail-closed, rather than silently misattributed.

Real GitHub regression tests use synthetic mirror references. The optional
native-wheel smoke creates a genuine upstream EventDataset, whose object
identity behavior is documented in the upstream source, but **the actual
installed wheel smoke is still unexecuted** in this workspace. The
research output remains descriptive, unauthenticated and nonproduction;
this ownership check is not independent proof of provider or event rights.

## 8. One-command local-only native acceptance and evidence boundary

To eliminate several separate human commands after a wheel and its
dependencies have been **independently approved and installed into a
throwaway virtual environment**, run the checked-in acceptance entrypoint:

```sh
python -m ops.kloppy_native_smoke_acceptance \
  --wheel /approved/wheels/kloppy-3.19.1-py3-none-any.whl \
  --receipt /approved/private-audit/kloppy-native-smoke.json
```

It performs, in order: official wheel SHA-256/ZIP preflight; checks exact
installed `kloppy==3.19.1`; runs the **actual native class** smoke module
as a separate Python test process with a disposable HOME, 180-second limit
and without environment-based provider keys or `PYTHONPATH`; reads the
unittest stderr summary and rejects nonzero exits, missing/zero tests or
skips. On all paths it records `production_recommendations: DISABLED`,
`forward_samples_certified: 0`, and all independent authenticity,
provider-data-rights and market-edge flags `false`. Receipt is a
600-mode exclusive-created local JSON file and is **self-reported test
evidence only, not an independent signature or certification**.

The entrypoint neither downloads nor installs packages and never invokes
provider data loaders. If it cannot access an exact official wheel or finds
an incompatible environment, it exits nonzero and reports `HOLD`.
The GitHub repository's normal CI only executes this entrypoint's
**mock/synthetic test cases**; those mock successes are not the real-wheel
acceptance test. Do not print or upload raw event data, access keys,
the actual local wheel, or filesystem paths in public PR comments.

This local protocol should only be considered complete when a reviewer
inspects an actual isolated-environment run that separately demonstrates
its approved dependencies, wheel hash, native smoke exit status and
nonproduction research-only output. Because its success flag is self-issued,
this local run does **not** satisfy the independent human-approval gate.


## 9. Real Kloppy wheel smoke run — 2026-11-15 (supersedes earlier "not run")

**Result: genuine upstream package installed and native-object tests executed
in a separate, ephemeral Firecrawl-hosted Linux sandbox, not in GitHub
Actions, production, a user's Codespace, or the user's local machine.**
Older "not run" text above records the previous unexecuted state and is
superseded for native runtime compatibility by the result here. This is
developer-run, self-reported research evidence; it is **not independent
approval of package provenance, its transitive dependencies, provider data,
model calibration or a betting system**.

Concrete evidence:

- GitHub VNext code inspected at immutable Draft PR #470 head
  \`11ec77e3e66dc5bad47e46757ef96073aaf49bf1\`. All seven relevant
  source/test files fetched by immutable raw GitHub URLs and verified
  independently against their Git blob SHA-1 from the GitHub connector,
  *before* running tests. No private repository credentials or provider
  secrets were supplied to the external sandbox.
- Downloaded the **real** PyPI artifact
  \`kloppy-3.19.1-py3-none-any.whl\`: **30,133,667 bytes**, SHA-256
  \`bdb468cc7b23a6c58276fdd8dbdb9c331e8cf4be8b721fdb97b7ec69d186b5ba\`
  (matches published PyPI SHA-256).
- Built a fresh Python 3.11 virtual environment, installed the exact
  Kloppy 3.19.1 wheel and resolved its runtime dependencies. \`pip check\`
  returned \`No broken requirements found.\` Actual imports of
  \`EventDataset\`, \`PassEvent\`, \`ShotEvent\`, and \`GenericEvent\` worked.
- **First genuine test run failed:** The existing wheel preflight was
  too strict for a **73,041,156-byte uncompressed official package member**
  (the old per-entry limit was 64 MiB). Real \`GenericEvent\` construction
  also required the explicit \`result=None\` and \`qualifiers=None\`
  parameters. Both were observed from the real installed package, not
  inferred from synthetic mocks.
- Fixed the guard to **96 MiB per entry**, keeping aggregate/ratio/path/
  symlink and exact PyPI hash gates unchanged. Corrected native
  \`GenericEvent\` fixture to supply \`result=None, qualifiers=None\`.
  Added a size-envelope regression test. Both changes committed in
  **the same Draft PR**, not in \`main\`.
- **Second genuine run at exact code head \`11ec77e...\`:**
  \`python -m ops.kloppy_offline_wheel_preflight --wheel <official wheel>\`
  returned \`LOCAL_WHEEL_HASH_MATCHES_PYPI\`;
  \`python -m unittest ops.tests.kloppy_native_real_smoke -v\`:
  **2 tests, OK**;
  \`python -m unittest ops.tests.test_kloppy_offline_wheel_preflight
  ops.tests.test_optional_kloppy_event_research -v\`:
  **32 tests, OK**;
  \`python -m unittest ops.tests.test_kloppy_native_smoke_acceptance -v\`:
  **11 tests, OK**;
  \`python -m ops.kloppy_native_smoke_acceptance --wheel <official wheel>
  --receipt <private ephemeral receipt>\`:
  \`RESEARCH_ONLY_LOCAL_SMOKE_PASSED\`, \`local_native_test_count=2\`.
  \`pip check\` still passed.
- Separately, GitHub Actions at \`11ec77e...\` showed **7/7 standard
  check-runs passing**. **Those standard GitHub CI checks did not run
  the external real-wheel installation test**, and should not be cited
  as if they had.

The receipt stays local to the ephemeral sandbox; no provider event files,
odds, keys or large wheel binaries were added to the public PR. Reproduction
in an approved runner should repeat hash verification, dependency/security
review and the same installed-native smoke. This is not evidence that
installed transitive dependencies are pinned, fully audited, trusted-publisher
attestations independently verified, or lawful event data available.

**State remains nonproduction: HOLD, DISABLED, Draft PR open/unmerged,
forward_samples_certified=0, positive_ev_verified=false.** GitHub
\`main\` protection, independent human code review and data rights
requirements still block promotion (Issue #439).


## 10. Reproducible 17-wheel offline dependency closure (2026-11-15)

**Result:** The actual upstream Kloppy 3.19.1 wheel and **all 16 resolved
runtime dependencies** were downloaded as wheels in a disposable Python
3.11 / Debian 12 x86_64 environment. Their individual **real file SHA-256**
hashes and versions were frozen in the research-only lock:

\`ops/research_locks/kloppy-3.19.1-cp311-linux-x86_64.txt\`

The repo lock has precisely 17 pinned \`name==version --hash=sha256:...\`
entries; the exact Kloppy wheel hash matches official PyPI's published hash
\`bdb468cc7b23a6c58276fdd8dbdb9c331e8cf4be8b721fdb97b7ec69d186b5ba\`.
Lock syntax and namespace are covered by the standard-library-only
\`ops/tests/test_kloppy_research_wheel_lock.py\` (five tests).

### Actually executed locked installation

An external, ephemeral sandbox verified all six relevant source/lock
files against GitHub's immutable blob SHAs at PR #470 commit
\`810e6a7cf9bc4135980fb64e8c3d9e8115a8b8cf\`.
A **new**, separate Python 3.11 venv then executed:

\`\`\`sh
python -m pip install --no-index --no-input --only-binary=:all: \
  --find-links=/private/approved-wheelhouse --require-hashes \
  -r ops/research_locks/kloppy-3.19.1-cp311-linux-x86_64.txt
python -m pip check
python -m unittest ops.tests.test_kloppy_research_wheel_lock \
  ops.tests.kloppy_native_real_smoke -v
python -m ops.kloppy_native_smoke_acceptance \
  --wheel /private/approved-wheelhouse/kloppy-3.19.1-py3-none-any.whl \
  --receipt /private/private-research-acceptance.json
\`\`\`

*The absolute paths in this block are illustrative; the same commands
were run against ephemeral \`/tmp\` directories containing the downloaded
wheels. The only network activity was the prior wheel download. The
installation itself used \`--no-index\` and had no network index.*

**Observed result:** pip installed all 17 exact wheels with hashes;
\`pip check\` reported \`No broken requirements found.\`;
five lock-structure tests **OK**; genuine installed Kloppy native smoke
**2 tests OK**; the acceptance receipt reported
\`RESEARCH_ONLY_LOCAL_SMOKE_PASSED\`,
\`wheel_sha256_verified_locally=true\`, \`local_native_test_count=2\`,
\`production_recommendations=DISABLED\` and
\`third_party_dependencies_independently_audited=false\`.

**Hash-rejection control also tested using real pip:** changing only
the Kloppy hash in a throwaway copy of the lock to 64 zeroes then running
\`pip download --no-index --require-hashes\` against the same real
wheelhouse failed exit code 1 with the official-wheel hash mismatch.
No wheelhouse binaries, licenses, secrets, raw match data or local receipts
were committed to GitHub.

### Installation on another machine (research only)

On the **same** CPython 3.11, Linux x86_64, with an explicit trusted
package-source decision, acquire the wheels via:

\`\`\`sh
python -m pip download --only-binary=:all: --require-hashes \
  -r ops/research_locks/kloppy-3.19.1-cp311-linux-x86_64.txt \
  -d /private/approved-wheelhouse
\`\`\`

Then disconnect from the network and run the local commands above.
A missing or differently built wheel must **fail**, not silently replace
the pinned wheel. This lock is deliberately platform-specific and **must
not** be assumed to install on CPython 3.12, macOS, Windows, ARM or a
production runtime.

### Outstanding approval gates

PyPI wheel METADATA of the 17 distributions advertises combinations of
BSD-3-Clause, MIT, Apache-2.0 and PSF-2.0 licenses, in both SPDX expressions
and human-readable legacy labels. **These are package-supplied claims,
not an independent per-dependency license/security/legal audit.**
The lock protects the identity of chosen archive bytes; it does not
establish that all packages are vulnerability-free, attest supplier
identity, check dependency source code, grant provider event-data rights
or certify any model, prospective match or value bet.

Keep the package lock and this run **research-only** until independent
dependency, code and data rights reviews succeed. Retain PR #470 Draft,
\`HOLD\` and \`production_recommendations=DISABLED\`; main governance
requirements (Issue #439) have not been waived.
