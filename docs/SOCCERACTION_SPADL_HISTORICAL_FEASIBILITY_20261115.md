# Socceraction 1.5.3 → SPADL historical research feasibility

**Date:** 2026-11-15 UTC. **State:** RESEARCH ONLY / HOLD /
`production_recommendations=DISABLED`. Zero forward-certified samples; no xT
or VAEP model trained, no model evaluation, no executable odds, no positive EV.

## Public software and data terms

- [Socceraction upstream repository](https://github.com/ML-KULeuven/socceraction)
  and [MIT license at version v1.5.3](https://github.com/ML-KULeuven/socceraction/blob/v1.5.3/LICENSE.rst):
  copyright KU Leuven Machine Learning Research Group; software license
  permits use with license/attribution conditions. The upstream project
  requests credit of its DTAI Sports Analytics lab in derived work
  ([FAQ](https://socceraction.readthedocs.io/en/stable/documentation/faq.html)).
- The public [StatsBomb Open Data README at immutable commit](https://github.com/hudl/open-data/blob/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/README.md)
  makes a **public football research** sample available with StatsBomb
  attribution and logo requirements. Its availability is not an independent
  grant of commercial betting, mass training, data redistribution, private
  provider access, or ongoing feed rights. Obtain separate terms for those
  use cases.
- [Socceraction data docs](https://socceraction.readthedocs.io/en/stable/documentation/data/statsbomb.html)
  explicitly support `StatsBombLoader(getter="local",root=...)` and SPADL
  conversion. No website fetching or provider tokens are needed **inside**
  the checked-in offline research entrypoint.

## First actually executed historical sample

The test used **exact official StatsBomb historical match ID `3788741`**
(Turkey vs Italy) from `hudl/open-data`, git commit
`4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`:

| Public historical file | Size | Real SHA-256 |
| --- | ---: | --- |
| `data/events/3788741.json` | 3,208,593 bytes | `b9ddce6bee771bdb1f3564c9ac0552619257e412d0767939f1e7f1500ace3062` |
| `data/lineups/3788741.json` | 19,491 bytes | `5874bcd25f9c75b12ebcf14b1fa46507a349ac4de822ffe07f876d2edbe0cfca` |

Every byte was verified before loading, and only in a disposable isolated
external Python 3.11 Linux research sandbox. Provider raw files were **not**
added to this GitHub PR or CI artifacts.

**Actually verified Python runtime:**
`socceraction==1.5.3`, `kloppy==3.19.1`,
`pandera==0.17.2`, `multimethod==1.12`,
`pandas==2.3.3`, `numpy==1.26.4`.
`pip check` returned `No broken requirements found.`
These observed versions are **not a complete hash-locked software supply-chain
approval**. Versions may not work on other Python/OS builds.

**Working conversion:** local StatsBombLoader converted **3,803 provider
event records** into **2,206 SPADL standardized on-ball actions**. Example
action-category counts in the real dataframe:

| SPADL action type | Count |
| --- | ---: |
| pass | 944 |
| dribble (SPADL category) | 915 |
| shot (SPADL category) | 27 |
| interception | 60 |
| other action types | 260 |
| **Total** | **2,206** |

SPADL conversion filters/derives actions, and these categories are not
directly comparable with native Kloppy event counts (3,911), nor are they
xG or xT numbers. The standardized event locations were in bounds of
SPADL's 105×68 m pitch. `team_id` values were `909` and `914`; all
converted actions have game ID `3788741`. This is purely a **post-match
descriptive transformation**, not a pre-match forecast.

## Discovered upstream compatibility problems (do not silently hide)

1. Fresh `socceraction==1.5.3` with its resolved
   `pandera==0.17.2` and `multimethod==2.1` failed on import:
   `ImportError: cannot import name 'overload' from 'multimethod'`.
   An isolated **research-only** environment with
   `multimethod==1.12` fixed imports and passed `pip check`.
   Do **not** downgrade/override the real deployment runtime without
   independent dependency/security tests.
2. Even after imports succeeded,
   `socceraction.spadl.kloppy.convert_to_actions` on a real installed
   `Kloppy==3.19.1` `EventDataset` failed with
   `TypeError: _SoccerActionCoordinateSystem() takes no arguments`.
   That direct pathway remains **NOT VERIFIED / HOLD**. Do not patch
   third-party code or manufacture SPADL numbers to disguise it.
3. The separately documented,
   officially supported `StatsBombLoader(getter="local")` plus
   `socceraction.spadl.statsbomb.convert_to_actions` **worked** on
   the same exact hash-checked historical event JSON. Some pandas
   FutureWarnings and inferred StatsBomb coordinate fidelity warnings were
   logged; the observed conversion passed basic geometry/identity checks,
   but source coordinate fidelity was **not independently certified**.

## Code and repeatability boundary

`ops/socceraction_spadl_offline_research.py` uses the same immutable
sample file hashes and native match identity as the earlier successful
Kloppy research smoke. It verifies **both local files' exact bytes before
importing** optional third-party packages, then uses a disposable private
StatsBombLoader directory. Its output is only summarized, never raw event
content or trained models.

It validates: expected two team IDs, exact match ID, local file SHA,
action ID continuity, per-period monotonic time, non-null bounded SPADL
pitch coordinates, supported periods and action count. An unrelated match,
bad file hash, missing package, wrong version or malformed action **fails
closed**, no partial summary.

The exact code at Draft PR #470 was downloaded from immutable GitHub
commit `fd920e33d1e4ffb10ff37c63d8528f0566232909`, checked against
the GitHub object blob SHA, and run against the real historical files.
**13 standard-library contract tests** also passed in the sandbox,
but those 13 tests use synthetic action rows (not actual event files).
GitHub CI runs those synthetic tests; the real-file smoke was executed
**separately**, not inside production or CI.

To reproduce in a separately approved isolated research environment
(with a separately reviewed dependency wheelhouse, no provider keys):

```sh
python -m ops.socceraction_spadl_offline_research \
    --events /approved/local/events/3788741.json \
    --lineups /approved/local/lineups/3788741.json
```

The output always reports
`status=RESEARCH_ONLY`,
`post_match_description_only=true`,
`kloppy_to_spadl_converter_verified=false`,
`xt_model_trained=false`,
`vaep_model_trained=false`,
`predictive_accuracy_improvement_verified=false`,
`positive_ev_verified=false` and
`production_recommendations=DISABLED`.

## Next research gate, not yet achieved

Before even considering xT/VAEP action valuation, secure explicit data
permissions for that use, a reviewed locked dependency closure, and a
chronological **many-match** independent training/evaluation design.
A single already-played match is insufficient for estimating reliable
generalizable xT/VAEP or a betting advantage. No automatic model
promotion or quantitative edge claims are permitted.

The governance blockers [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439)
(protected main and independent review) remain outstanding; Draft PR #470
must not be merged based on this isolated SPADL smoke.
