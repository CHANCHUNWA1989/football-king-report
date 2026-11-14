# Open-source integration audit — research branch (2026-11-08)

This file records projects inspected for lawful and testable reuse. **No third-party source files have been copied into this repository by this audit.** Do not merge into main solely because CI is green.

## Verified upstream licenses

| Project | License file checked | Integration decision |
| --- | --- | --- |
| [martineastwood/penaltyblog](https://github.com/martineastwood/penaltyblog) | [LICENCE](https://github.com/martineastwood/penaltyblog/blob/master/LICENCE): MIT, copyright 2021 Martin Eastwood | Continue the existing **optional dependency adapter**; do not vendor a second implementation. Preserve MIT attribution if any code is copied in the future. |
| [probberechts/soccerdata](https://github.com/probberechts/soccerdata) | [LICENSE.rst](https://github.com/probberechts/soccerdata/blob/master/LICENSE.rst): Apache-2.0, copyright 2021 Pieter Robberechts; includes third-party footballdata MIT notice | Candidate **opt-in historical data provider** only. Verify individual source website terms, robots policies, schema, capture timestamps, coverage, and local data rights first. No scraping or runtime integration was added here. |

License inspection does **not** grant rights to any independently licensed data obtained through the package. Prefer package dependencies/adapters over copying. Check actual installed versions and transitive dependencies before production. No claim that external code is better at prediction without out-of-sample empirical evidence.

## Existing local safeguards (research branch)

- Optional Poisson and Dixon–Coles research challenger and paired forecast comparisons.
- Chronological, paired offline scoring with small-sample uncertainty warnings.
- Sealed forecast snapshots, local exclusive-create archive, strict outcome joining.
- Ed25519 receipt verification, trust allowlist, and historical key diagnostics.
- RFC 3161 request encoder. **RFC 3161 TSA response verification and independently authenticated historical timestamp are not implemented.**
- Production betting recommendations remain **DISABLED**.

## Highest-priority missing capabilities

1. **Real point-in-time data:** capture lawful, source-attributed market odds, fixture and lineup changes, timestamps, and verified results; create retention policy and access controls.
2. **True historical provenance:** trusted external timestamp/CMS verification, certified TSA identity, signed fixture and result origin. A self-claimed timestamp is insufficient.
3. **Honest model evidence:** leakage-safe rolling out-of-time benchmark; sufficient sample per market; calibration; price/closing-line comparison; independent baseline; uncertainty and multiple-comparison handling.
4. **Operational robustness:** source availability and schema-drift tests, schema adapters, retries, logs, bounded costs, privacy/secrets scanning, and de-identified audit reports.
5. **Deployment gate:** independent CI and code review, license/terms check, reproducible empirical validation, manual authorization. No automatic promotion or live betting.

## Explicit guardrails

Never copy private/proprietary code, credentials, user data, or third-party data without permission. Keep Apache NOTICE and attribution obligations, and preserve MIT notices for copied substantial code. Do not equate passing synthetic tests with positive EV. Do not claim bookmaker prices or live results unless collected from an authenticated real data source. Maintain `production_recommendations: DISABLED` and do not merge this research branch into `main`.
