# PR #460 — Real historical archive versus Penaltyblog paired forecast gaps (2026-11-15)

**Scope:** read-only, offline research provenance check. **HOLD / DISABLED** regardless of result. No merge, rollout, betting, or forecasting from historic labels.

## Actual GitHub records examined

GitHub `CHANCHUNWA1989/football-king-report` contained two different **real tracked** archives, not interchangeable copies:

| Git source ref and pinned blob | Historical settled rows | `p` / `m` | `ab` | `c` | `forecast_event_id` | `source_fixture_identity` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `main`, Git blob `c8d8fadf4b7edbe9613d760cde868e96e9bcd4ac` | 104 | 104 / 104 | 91 | 65 | 38 | 9 |
| PR #460 branch archive, Git blob `068297b829393f768ced2983fe9ab60c1f0e6a28` | 82 | 82 / 82 | 69 | 43 | 16 | 1 |

The `main` archive's blob ID was confirmed from GitHub `fetch_file`; the GitHub Actions PR merged-ref checkout must match this **specific** 104-row blob for the pinned real archive job to pass. If an automated `main` update changes the archive, the pin is intentionally invalidated. Do not silently repin it without reviewing the changed archive.

**These are archived research records, not a certified prospective cohort.** Source file labels `p` and `m` denote model and market 1X2 probability vectors, not a verified original A forecast source/market executable quote. The documented `ab_model` is `probability-shrink-to-uniform-fixed-0.15-v1`, and `c_model` is `market-anchored-fixed-25pct-model-75pct-consensus-v1` — **NEITHER is Penaltyblog Poisson or Dixon–Coles**.

The archive does not carry authentic matched `penaltyblog` forecast output from PR #458, same-cutoff Penaltyblog per-fixture model-produced timestamps, source-last-received timestamps, externally signed forecast witnesses, publisher-authenticated final results, or executable bookmaker quote certificates. `forecast_event_id` and `source_fixture_identity` are **self-declared fields**, not sufficient independent provenance.

## What changed

- `ops/paired_real_archive_gap_audit.py`: read a local exact JSON archive, validate its supplied **pinned Git blob SHA-1**, schema, clocks, fixture key, p/m/ab/c shapes, original challenger labels, and disabled flags; enumerate only aggregate missing capabilities; never issue source-certification or scores.
- `ops/tests/test_paired_real_archive_gap_audit.py`: synthetic adversarial tests for altered-but-rehashed records, fake certification, malformed/archive drift, false Penaltyblog labels, bool outcomes/probabilities and cross-fixture IDs.
- Dedicated **read-only CI job step** in `.github/workflows/paired-challenger-comparison.yml`: run tests, then audit `evidence/settled.json` at the pinned GitHub `main` archive blob. A mismatch fails closed. The exit code 0 denotes **a complete diagnostic inventory under HOLD**, not source or model certification.

Run locally against the exact archive bytes from a separately selected GitHub immutable revision:

```sh
python -m ops.paired_real_archive_gap_audit \
  --archive /approved/research/exact-main/evidence/settled.json \
  --expected-git-blob-sha1 c8d8fadf4b7edbe9613d760cde868e96e9bcd4ac
python -m unittest discover -s ops/tests -p test_paired_real_archive_gap_audit.py -v
```

**Git blob SHA-1 relative identity is NOT third-party authenticated match source, independently witnessed capture time, or independent legal clearance.** Do not treat a computed SHA of a self-written file as a secure historical timestamp or provider signature. No raw licensed provider bytes were added.

## Acceptance / blocker

1. Independently lawful, pre-match A/Poisson/Dixon–Coles fixture outputs **with native source namespace, exact kickoff, same UTC cutoff, complete model input data and matching result identity**. Do not reclassify the archive's `ab` and `c` fields.
2. External trusted capture/producer proof (Rekor/TSA) and rights-approved original result/quote source, with independent relationship checks; genuine forward cohort and predeclared OOS benchmark.
3. Genuine authorized independent PR review and branch protection ([Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439)).

**No accepted Penaltyblog-vs-original real paired samples, certified prospective samples, positive EV, trustworthy lift or rollout are demonstrated.** PR #460 remains **DRAFT, HOLD / DISABLED** and unmerged; no changes to `main`.
