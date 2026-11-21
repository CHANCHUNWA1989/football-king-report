# PR #458: Original A shadow + same-GET source byte-identity linkage

Date: 2026-11-15 (UTC). All logic is **OFFLINE RESEARCH ONLY**, Draft, HOLD/DISABLED and unmerged. No real-world bets, source entitlement, Sigstore certification, or automatically scheduled capture.

## What this adds

The already-existing optional `ops/shadow_forecast.py --raw-capture-dir` preserves the **actual one-GET** response bytes in an owner-private, atomic, immutable SHA256-named tar. The shadow `sources` record stores the same GET's candidate raw digest and the original source bundle digest. That alone does NOT securely bind each of the shadow forecast rows to exactly the fixtures in the saved original body.

`ops/original_a_same_get_shadow_pair.py` now supplies an additional **opt-in, offline, fail-closed** linkage:

1. Reopen the original source private tar via `original_a_same_get_private_seal.check_private_bundle` for a complete hash/manifest/canonical-tar replay; reread original raw response bytes. **No HTTP request, provider scraping, or synthetic backfill.**
2. Reopen the exact original A JSON shadow file and check the original A live generation start/end timestamps and source's same-GET SHA256, private bundle digest, declared source capture, and original raw private seal time <= A's own completion.
3. For **every** Bundesliga A forecast (rather than choosing only surviving good rows), match the exact raw OpenLigaDB response's **typed native matchID, leagueId, leagueSeason, home/away teamId, display names for contradiction detection only, and kickoff UTC** against A's retained typed source metadata. Refuse duplicate match IDs, missing original rows, bad 1X2 probabilities, missing original training-input digest, changed team orientation, future kickoff contradictions, absent native IDs, forged certification and any other incomplete row. Only the already-supported OpenLigaDB Bundesliga scope is accepted.
4. Create a *new*, owner-private **0600** canonical two-file tar (`shadow.json` exact unchanged bytes, `link.json` original event-ID/native-ID/time/probability-level links and SHA256 references). This tar explicitly **does NOT duplicate the raw response bytes**, which remain inside the separate private canonical original tar; both SHA256 values are necessary for a full replay. Both file subjects are never overwritten; the new link tar is atomically no-replace published into a separate existing private directory (0700). New data is never added to public Pages or the repository.
5. The `replay` operation reopens the link tar and original source tar, checks their SHA256 values and retests **every fixture** from the original shadow bytes. Both original source tar and link tar must remain available. No stored verification flag or downloaded `verification.json` is trusted as an independent signature witness.

### Manual offline example only (not executed against licensed live data)

```sh
umask 077
mkdir -m 700 /private/research/a-source
mkdir -m 700 /private/research/a-links

# In an authorized live original A runner, explicitly enable source preservation:
python ops/shadow_forecast.py \
  --output /private/research/a-shadow.json \
  --raw-capture-dir /private/research/a-source

# Only after obtaining the original unmodified shadow JSON and its corresponding
# source SHA256 from the shadow's sources[].private_same_get_bundle_sha256_unattested:
python -m ops.original_a_same_get_shadow_pair \
  --shadow /private/research/a-shadow.json \
  --original-dir /private/research/a-source \
  --pair-dir /private/research/a-links \
  --source-bundle-sha256 EXACT_SHA256_FROM_THIS_SAME_A_RUN
```

All paths and placeholders are illustrative; the research PR's CI runs **only synthetic**, no real API calls or forecasting. The source/private shadow files must be kept private, not uploaded to public artifacts or included in PR commits. No actual source hash is claimed from the example.

## Tests / trust limits

`ops/tests/test_original_a_same_get_shadow_pair.py` includes synthetic original OpenLigaDB response bytes, original A shadow metadata and private source tar, then tests successful **local** byte-binding still HOLD, exact full replay, tampering after first creation, duplicate original match IDs, swapped native teams, missing match/IDs, wrong kickoff, stale or false origin flags, Boolean 1X2 vectors, missing training digest, symlink/hardlink and unsafe directories, duplicate no-overwrite and partial-file prevention.

Tests are wired to the research-only `.github/workflows/penaltyblog-two-model-pipeline.yml` job; existing real Penaltyblog smoke remains synthetic and still separate from model scoring.

**Not verified:** original publisher author authenticity, licence entitlement, original sender authenticity, network trust, independent capture/forecast UTC clocks, Sigstore/Rekor/TSA records, verified real odds, final score, independent same-cutoff prospective A/Poisson/DC trials, forward model improvement, EV or ROI. A SHA-256 may securely link local bytes but cannot make an independently attested future capture appear retrospectively.

Next legitimate stage: an authorized live owner-private original A capture, matched exact raw and A output, then **original-main** attestation subject signing and **fresh** independently verified signer/witness execution. Existing `ops/openliga_capture_provenance.py` and `ops/forecast_provenance_audit.py` demonstrate the correct trusted CLI boundary but should not be treated as authorizing the new private tar format without audit and signing-policy changes.

Governance remains [Issue #439](https://github.com/CHANCHUNWA1989/football-king-report/issues/439): protect main, require current-head independent human review and CI before any safe merge or release. Maintain `status=HOLD`, `production_recommendations=DISABLED`, `certified_prospective_samples=0`, `positive_ev_verified=false`.
