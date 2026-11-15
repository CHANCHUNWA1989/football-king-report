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
