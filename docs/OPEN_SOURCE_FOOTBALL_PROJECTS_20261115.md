# GitHub football analytics integration review — 2026-11-15

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
