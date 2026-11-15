# PR #458 — Optional exact original A same-GET source preservation

2026-11-15. **Research only; OPEN / DRAFT / HOLD / DISABLED.** Main branch, public forecast and scheduled workflows have NOT been enabled or edited.

## Why this update

[The previous real 2026-11-15 cross-run audit](./VNEXT_A_OPENLIGA_CROSSRUN_PROVENANCE_20261115.md) replayed two separately archived GitHub files. Source gzip bytes and A shadow gzip bytes were genuine Git-pinned objects, but the separate OpenLigaDB capture **completed after** the selected A forecast with 29 predictions. This cannot prove those 29 model inputs existed before that original forecast, and cannot be backfilled into a genuine pre-match cohort.

In the original `ops/shadow_forecast.py`, the OpenLigaDB gateway already obtains exact raw HTTP bytes once, through `buffered_opener`, and uses the same bytes to normalize predictions and retain native IDs. Previously it discarded the raw bytes after returning. This change adds an **explicit opt-in** local-only preservation of *that exact original body*, without sending another HTTP request.

## New code

- `ops/original_a_same_get_private_seal.py`: original bytes and a minimal H/O-L-D metadata manifest in a single canonical private tar file. The manifest records raw byte SHA256, gateway's already observed but **unattested** `captured_utc`, local untrusted seal time, OpenLigaDB/Bundesliga namespace, and explicit false independent signer / publisher / scoring flags.
- Atomic output via a mode-0600 staging file, fsync, then `os.link` publication **only if the final SHA256-named target does not already exist**; no overwrite or follow-symlinks. Requires an existing absolute private directory owned by the invoking user with mode **0700 or more restrictive**, not a public directory. No raw files are committed by this PR. No external attestation or signed time is created.
- `ops/original_a_same_get_private_seal.check_private_bundle` re-opens only the exact private tar and re-verifies source and bundle hashes and canonical member structure. Local replay is relative integrity only, not authenticity or independent time.
- `ops/shadow_forecast.py` extends the original *one GET* normalized collector with `raw_capture_sink` callback. The source must already have `READY_RESEARCH`, matching gateway SHA256, and at least one same-response typed native OpenLigaDB fixture identity; even a READY response with no native identity is rejected, and failures HOLD the Bundesliga league. A new optional `generate(..., raw_capture_dir=...)` passes that sink only for native, **live** getter calls. Replay `generate(now=...)` or custom `getter` cannot claim same-source capture. The original CLI now accepts `--raw-capture-dir` only when expressly given. **Without the flag there is no additional I/O, network request or output change.**
- When enabled and valid, the original A shadow `sources` row gets an **unattested** private bundle SHA256 and same-GET source SHA256 (but no local path, no raw body and no source credentials). The original typed `native_fixture_input.raw_input_durably_archived` stays **false** — the system has not certified durable external custody. Nothing automatically promotes the model to valid scoring.
- `ops/tests/test_original_a_same_get_private_seal.py`: 24 synthetic tests, including exact in-memory one-GET reuse and no second HTTP request, no default private saving, replay/custom getter refusal, immutable private file re-opening, wrong hashes, future gateway-clock claims, aliases/hardlinks/symlinks, non-private directory refusal, binary tampering, duplicate no-overwrite, and private file permissions. These tests do **not** fetch real match data or verify GitHub signer certificates.
- `.github/workflows/penaltyblog-two-model-pipeline.yml`: run all 24 tests in research CI; no network is accessed by those tests. Existing real Penaltyblog dependency smoke remains separate and synthetic.

## Example only: manual, isolated research

From a separately authorized runner with a version of the original project available and lawful source use:

```sh
umask 077
mkdir -m 700 /private/work/original-a-source
python ops/shadow_forecast.py \
  --output /private/work/shadow.json \
  --raw-capture-dir /private/work/original-a-source
```

Paths are illustrative; the command has **not** been executed against a real public source by this PR. Keep files private; do not add to a public artifact, website or repository. The optional original collector has its existing network connection when executed in a live authorized runner; this pull request did **not** create a new fetcher or enable any new cron job.

The presence of a local tar, source SHA and local clock is **not** a Rekor/TSA witness or publisher attestation. A future trusted-source implementation must use the *existing* `ops/openliga_capture_provenance.py` and `ops/forecast_provenance_audit.py` original-main CLI verification (with proper source/subject and run binding), not a self-signed or saved verification flag. This local tar deliberately does not impersonate the canonical attested source tar schema.

## Still blocked and acceptance criteria

- **No new truly authenticated original A + Poisson/DC same-decision-cutoff pre-match cohort.** The optional private file is original same-request research data only, and could have been sourced from an unauthenticated publisher response or compromised machine. No independent Rekor/TSA is claimed.
- Both original A response and exact corresponding forecast output must be submitted via approved original-main signing workflow with independent timestamp witness, clear licensing, source-native fixture ID match, before-kickoff cutoff and verified historical training-data availability. Genuine lawful results and executable quote proofs are a distinct follow-up.
- [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439): protected `main`, required CI and independent human review must be established by an authorized repo administrator before any merge or deployment. PR #458 remains DRAFT, no permission escalation, bypass or production change.

Always `production_recommendations=DISABLED`, `positive_ev_verified=false`, `certified_prospective_samples=0`; no independently verified prediction uplift or EV was demonstrated.
