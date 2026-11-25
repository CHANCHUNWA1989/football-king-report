# P0 #569 — Legacy settlement Contents PUT failure diagnostics (offline pilot)

**Status: research only / NO production workflow modification / HOLD/DISABLED.**

## Observed evidence, no invented root cause

From the real failed [run #45149415323](https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/45149415323), `archive` job `137607665457` attempted to merge `evidence/settled.json` **five times** and finally exited 1. The incumbent `.github/workflows/football-king-iphone.yml` (around lines 955–990) discards the entire `gh api -X PUT ... >/dev/null 2>&1` response; its existing retry message asserts "concurrent" without proving an actual concurrent writer. We **cannot recover the HTTP code** from those existing logs. Possible 401/403/409/422/429/5xx are *hypotheses*, not evidence.

GitHub documents the [Contents API](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents) and `gh api --include` printing HTTP response headers. Different status codes imply different investigation paths, **not certified causes**.

## Research code (NO network and NO credentials)

- `ops/settlement_put_diagnostics.py` is a **pure diagnostic/parser**. It never calls `gh` or GitHub, writes to disk, edits Rulesets, sends network requests, or alters old data.
- Given the *first status line* of a **separately authorized and captured** `gh api --include` Contents PUT result and its actual CLI exit code, it prints **only**: numeric HTTP status (or null), allowlisted classification, exit-zero boolean, whether a success response was observed, and explicit `retry_root_cause_verified=false` / `production_recommendations=DISABLED`.
- **No raw API response, body, header, request URL, sha, token, auth error or environment data is emitted.** Oversized/invalid status lines fail to `HTTP_STATUS_NOT_CAPTURED`; contradictory exit/status combinations fail closed.
- `ops/tests/test_settlement_put_diagnostics.py` covers success, 401/403/404/409/422/429/5xx, missing/suppressed HTTP header, overlong/multiline/untrusted response, inconsistent exit code, and secret redaction.

### Fully offline example (safe; never updates GitHub)

```bash
printf 'HTTP/2.0 409 Conflict\n' |
  python -m ops.settlement_put_diagnostics --exit-code 1
```

Expected category: `CONFLICT_STALE_SHA_OR_CONCURRENT_WRITE_UNVERIFIED` with `retry_root_cause_verified=false`. **It does not prove GitHub returned 409 in the historical run**.

## Future independent admin-approved diagnosis / cutover

1. Review and authorize any future capture procedure **before** attaching it to a job that can write `main`. Disable shell trace, don't upload response bodies, and do not persist credentials, output buffers, request payload or raw error messages as artifacts. Discard captured bytes in ephemeral process memory after reading only the first HTTP status line. If `gh api --include` does not expose a status line for a failure, report `UNKNOWN`; never infer it from generic stderr.
2. Correlate a genuine observed HTTP code with contemporaneous protected-branch rules, exact file SHA at GET/PUT, token permissions, write actor, default-branch state and writer timestamps. A 409 is not automatically concurrent modification; 403 is not automatically Ruleset; 422 is not automatically malformed JSON.
3. No live test writes to main before independent Code Review and a verified backup/rollback plan. Prefer a synthetic canary on a **dedicated authorized archive ref**.
4. Only after #571 real write/read continuity, full consumer migration and human approval consider activation of strict no-bypass `main` policy (#439). Provider licenses and independent true odds/results/OOS proof (#452) remain unavailable.

**No historical error code was recovered.** Existing direct-main `archive_provenance` / `archive` writers remain unchanged, as do iPhone report consumers. Research-only `HOLD / DISABLED`.
