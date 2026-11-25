# P0 #569 — actual 35-file historical-byte manifest and iPhone dual-reader parity

**2026-11-24 HKT · research Draft PR #571 · HOLD / DISABLED.** This is an original-byte **source inventory**, not a report that the independent archive branch received any history. Nothing in this milestone writes `main`, the hosted archive ref, source pointers, GitHub Rulesets, iPhone public pages or betting recommendations.

## Real GitHub pinned evidence, not synthetic placeholders

Read-only connected GitHub observations:

- Source `main` at **`12155d9058a3709ccd0333bb103bbb8cce0e3cec`**.
- Hosted archive bootstrap `refs/heads/research/forward-provenance-archive` at **`3ce493fbeb9bfea29af1b93064a085afe8efb280`**.
- GitHub compare: `main` **16 commits ahead**, 0 behind, **42 changed paths** against that archive baseline; **35 added `.gz` paths** require explicit history-retention decisions. The previous **20-file** inventory was correct only at its **older** pinned `main` SHA; this document supersedes the count for the newer pinned pair.
- GitHub recursive tree at the newer SHA returned **`truncated=false`**. For the 35 added gzip paths, the returned tree exposes exactly **22 distinct Git blob IDs**, and the sum of path-level compressed sizes is **124,600 bytes** (duplicates count under each path).
- The actual compressed source bytes were retrieved through GitHub's pinned `base64` contents API for each **distinct** blob. SHA-256 was computed on the **raw compressed bytes** (not JSON decompression/recompression); repeated Git blob IDs were mapped to the same SHA-256 and byte length at every corresponding path. The SHA-256 implementation passed the known `abc` test vector, and one 74-byte live GitHub gzip was separately cross-checked with Python `hashlib.sha256` (same `5072b081...` value).
- Full SHA-256, 40-character Git blob ID and compressed size per path are committed in `docs/P0_569_PINNED_35_HISTORY_BLOBS_SHA256_2026_11_24.json` with **`remote_archive_copy_confirmed=false`**, **`independent_archive_retention_verified=false`**, and `production_recommendations=DISABLED`.

The real hosted archive branch still pointed to the **older bootstrap commit** at this observation: these newly added `main` paths were **not present there**. GitHub source-byte hashing is **not an archive destination byte-parity pass** and is **not cryptographic proof of a provider's signature, timestamp, licence or truth of a claimed football result**.

## Repeatable source-versus-archive gate

`ops/history_blob_retention_preflight.py` takes the pinned manifest, an offline local Git repository containing both historical commits and an explicit candidate archive SHA. It checks the complete `.gz` additions set between source/bootstrap, refuses manifest omissions, unsafe Git tree mode, missing or changed candidates, changed bytes with equivalent decompressed JSON, dirty worktree confusion, and Git redirections. The checks read exact committed Git **objects**, not mutable worktree copies; they cannot fetch remote refs or write any branch. Even byte-identical results return **HOLD / DISABLED** and do not attest hosted custody.

`ops/tests/test_history_blob_retention_preflight.py` already tests the source and candidate gate against temporary local Git repositories. `ops/tests/test_pinned_35_history_manifest_contract.py` additionally tests the **real pinned** manifest's 35 paths, 22 distinct blobs, all history families, identical repeated-blob digests and refusal of safety-flag promotions.

## Existing iPhone two-report builder checks — actual checked-in legacy research, offline only

The research branch already includes `ops/tests/test_four_writer_mobile_read_parity.py` and `ops/tests/test_mobile_settlement_parity_preflight.py`, which invoke the actual iPhone public-readiness and daily-scorecard builders against the checked-in `evidence/settled.json` **105+ original research rows**, then append **one clearly synthetic, independently unverified row** inside a temporary local bare-Git archive. Both candidate builders agree on `N+1` only when supplied the **same** canonical cumulative settlement input; historic-row drop/rewrite, dirty compressed batch and untracked batch tests reject inconsistent inputs. The original `evidence/settled.json` bytes stay unchanged.

**The deployed iPhone workflow is NOT switched:** `public_readiness_site` currently reads `main:evidence/settled.json` while `forward_daily_scorecard` reads the run-local `$RUNNER_TEMP/settled.json`. This is a real **reader split** when new archive rows exist. The offline same-input parity preview proves a *candidate*, not actual iPhone or Pages cutover. It does not authenticate current production match/market evidence or verify independently settled results.

## External acceptance blockers — do not bypass

1. An independent nonauthor reviewer must review these exact SHA-indexed source manifests, archive candidate path contract, legacy research baseline and iPhone reader transition. PR #571 had **0** independent reviews at this milestone.
2. Repository admin must independently enforce archive protection against force/delete and audit bypass actors, and establish writer identity demonstrably unable to change `main`. Observed public `main` protection is **false** and repository Rulesets **`[]`**. Existence of a public archive branch is **not sufficient**.
3. Only after those controls and source rights are approved may a separately authorized **synthetic-only hosted** remote write/readback canary be designed. Actual production publisher migrations involve 15 `contents:write` workflows (including four direct-main Git-push blocks), mutable latest pointers, cross-source licences, and historical iPhone/Pages consumers. They have not been deployed from this research PR.
4. Review future `main` changes separately: the 35-file manifest is pinned to an exact SHA, **not** a claim that production history will stop changing. No force/reset/rebase/automatic archive backfill, automatic Ruleset activation or real-money betting.

**Decision: source fingerprint inventory complete at pinned SHA; hosted archive retention incomplete/unattested; iPhone public switch not performed. HOLD / DISABLED. Keep issues #569/#439/#452 open.**
