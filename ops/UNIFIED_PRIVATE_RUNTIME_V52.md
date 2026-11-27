# V52 private runtime — research only

Base V51 PR #749 exact head 0b36095c222798f471310645c829e823e19f535a: all five workflows successful. V52 connects private capture/storage (V47/V48) and private settlement/evaluation (V49/V50) with a single opt-in local CLI. The V44 live benchmark remains a separate path.

Prerequisites: authorized POSIX private runtime, licensed/authorized source access, private persistent directories outside repository (owner mode 0700), environment-provided PROPLINE_API_KEY for collection only. Never put keys in command arguments, commit raw inputs, upload output, or run in GitHub Actions. The registration clock and existing quota reserve apply unchanged.

From the research checkout:
```sh
python -m ops.research_private_runtime_v52 --authorized-private-runtime collect --store /private/runs --league bundesliga
python -m ops.research_private_runtime_v52 --authorized-private-runtime review --store /private/runs --result-store /private/results --run-sha <run-digest> --primary-sha <result-digest> --secondary-sha <result-digest>
```

Paths/digests are placeholders. Supply original authorized sanitized result snapshot bytes as <sha256>.json in the separate result directory, with mode 0600. Use repeated digest flags for the declared roster; omitted result digests yield unresolved cases rather than invented outcomes. No result collection is performed by review. The command checks file ownership, mode, regular-file and no-symlink/no-hardlink properties, digest, size, and bounded aggregate input, then V50 replays V48 runs and V49 settlement. No path or raw payload in aggregate review output. Output remains private. The local roster is selected by the operator, not proof of complete prospective coverage. Dual-result candidate coverage remains limited by existing source eligibility.

Ten synthetic test methods cover the actual saved-run-to-evaluation interface and mocked acquisition delegation, rejection of changed bytes, invalid permissions, symlinks, duplicate identities, missing credentials, incomplete evidence and shared CI runtime. No new provider calls, credential access, true external witness, independent prospective sample, deployment or calibrated model uplift. HOLD/DISABLED. Exact-head CI required.
