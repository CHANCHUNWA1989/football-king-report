# One historical match: native Kloppy 3.19.1 + StatsBomb Open Data smoke

**Date:** 2026-11-15 (UTC). **State:** RESEARCH_ONLY / HOLD /
`production_recommendations=DISABLED`. No release, model promotion,
data-feed commercialization or betting recommendation.

## Source, rights and scope

Source: **StatsBomb Open Data**, maintained in the official
[hudl/open-data repository](https://github.com/hudl/open-data).
The provider [README at immutable commit 4b73468f](https://github.com/hudl/open-data/blob/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/README.md)
describes public football research availability and requests **StatsBomb**
source credit and use of the official logo when publishing analysis. The
[official StatsBomb logo / Media Pack](https://statsbomb.com/media-pack/)
is the provider's branding source. Do not assume this public-research
permission authorizes commercial prediction products, gambling purposes,
training rights, redistribution, or use of private StatsBomb data;
independent terms review remains mandatory.

This test uses **one older historic sample match (official provider match
ID `3788741`) only**. It is not a prospective sample, model fit, or proof
of statistical accuracy. Provider JSON is downloaded only to a disposable
sandbox and is **not committed to GitHub or CI**.

GitHub data snapshot:

- Repository: `hudl/open-data`
- Source commit: `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`
- `data/events/3788741.json`: **3,208,593 bytes**,
  SHA-256 `b9ddce6bee771bdb1f3564c9ac0552619257e412d0767939f1e7f1500ace3062`
- `data/lineups/3788741.json`: **19,491 bytes**,
  SHA-256 `5874bcd25f9c75b12ebcf14b1fa46507a349ac4de822ffe07f876d2edbe0cfca`
- Each file's raw SHA-256 was computed from the actual bytes fetched
  from the official immutable upstream commit. Both contents were
  used only in the research sandbox.

## Actual research smoke run

The existing research-specific Python 3.11 Linux x86_64 environment used
**exact Kloppy 3.19.1**, installed from the SHA-256 locked 17-wheel set in
`ops/research_locks/kloppy-3.19.1-cp311-linux-x86_64.txt`.

The new optional `ops/kloppy_statsbomb_offline_research.py` accepts
only those **two already-local** exact JSON files, checks both hashes
and byte lengths *before* importing Kloppy, and supplies the verified
bytes through `BytesIO` to avoid local file replacement between hash
verification and parsing. It has **no fetching, installation, scraping,
credential use or outbound request**.

Reproduce (only for rights-cleared offline research, in an approved
isolated environment):

```sh
python -m ops.kloppy_statsbomb_offline_research \
  --events /approved/local/data/events/3788741.json \
  --lineups /approved/local/data/lineups/3788741.json
```

The output includes only a descriptive two-team pass/shot summary and
explicit flags: `status=RESEARCH_ONLY`,
`commercial_data_rights_verified=false`,
`positive_ev_verified=false`,
`model_promoted=false`, `production_recommendations=DISABLED`,
`source_data_rights_independently_verified=false`, and
`historical_sample_not_certified_prospective=true`.

### Native API issues discovered from actual provider data

1. **Missing game identity in local JSON path.** Native Kloppy
   `statsbomb.load(event_data=..., lineup_data=...)` returned
   `metadata.game_id=None`. Passing
   `additional_metadata={"game_id": "3788741"}` created a new outer
   `EventDataset` but left its events' `event.dataset` references
   pointing to the previous inner dataset. That correctly failed the
   strict parent-identity guard. **Safe fix:** after checksumming *both*
   files and loading without additional_metadata, set the mutable
   `dataset.metadata.game_id` in place; all original native parent
   references remain identical to the dataset.
2. **Legitimate foul + card dual record.** The official historic sample
   produced two pairs where native `FoulCommittedEvent` and
   `CardEvent` shared the **same provider event ID** and **the same
   underlying raw event object**. Earlier fail-closed code rejected
   every duplicate ID. The adapter now accepts only one
   `FOUL_COMMITTED` / `CARD` pair with identical raw record identity,
   team, timestamp, period and dataset. All duplicate passes/shots,
   third copies, cross-team/time/record combinations are rejected.

The data loader produced native event objects, and the hash-verified
VNext adapter returned **RESEARCH_ONLY** without errors. Exact GitHub
source/test code at commit
`4cd456ebdebe43240cde1cbd4b6757a13294d554` was downloaded and
matched to the repository's Git blob SHAs before running; the actual
Kloppy runtime/JSON smoke succeeded. The repo's standard CI does
**not** download provider JSON and verifies its contracts using
eight additional synthetic tests instead.

## Evidence limitations / remaining gates

This provider's *public research* terms do not establish commercial
licensing for betting or for the intended future production pipeline.
The source's commit timestamp and historical source availability are
not an independently witnessed pre-match ingestion. The output is not
an OOS test, independent score/odds verification, predictive edge,
or an EV estimate. **Certified prospective samples remain 0.**

Keep PR #470 DRAFT, OPEN and UNMERGED. Main branch protection and
independent code review remain blocked by
[Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439).
Do not package data JSON or vendor restricted provider files; do not
enable model training or automated bets.
