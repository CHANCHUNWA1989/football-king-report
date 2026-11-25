# P0 #569 — Isolated forecast provenance archive writer research pilot

**Status: Draft research only / HOLD / production DISABLED.** This is a local Git behavior pilot, not a deployed archive migration. It adds no Actions event, credential, scheduled task, remote branch, main code write, model input, API call, or betting recommendation.

## Root conflict and observed evidence
The existing `.github/workflows/football-king-iphone.yml` job `archive_provenance` pushes the run's immutable 10-file proof directly to `refs/heads/main`; `archive` also pushes to main and PUTs `evidence/settled.json`. Run #45149415323 confirmed a successful direct-main provenance commit while `archive` failed five settled-file PUT retries. A strict PR-only main ruleset with zero bypass would reject these legacy writes. Do not activate Stage 1 rulesets until **all direct-main writers** are migrated and the readers are compatible.

## Pilot code

- `ops/isolated_provenance_archive.py`: opt-in CLI `python -m ops.isolated_provenance_archive --repo <checkout> --proof <run-artifact-directory> --run-id <id> --attempt <id> --day YYYY/MM/DD`.
- **Destination ref is fixed** to `refs/heads/research/forward-provenance-archive` and **must exist in advance**. This code refuses to bootstrap the remote branch. It never writes to `main`, never uses force, and does not alter repository Actions or configure GitHub auth.
- Fetch exact remote branch head. Use isolated temporary Git worktree. Reuse the existing `ops.archive_forecast_provenance.prepare` ten-file, allowlisted, size-checked, immutable raw-byte packer. Create one commit and push **only** to the fixed archive branch with normal fast-forward semantics. Non-fast-forward races retry with fresh state. An identical replay returns `ALREADY_ARCHIVED`; changed bytes for an existing run ID fail closed without overwrite.
- The CLI prints only status, count and fixed branch metadata; no raw evidence, secrets or provider bytes. All outcomes retain `production_recommendations=DISABLED`. Caller must provide configured credentials after independent review; none are in this pilot.
- `ops/tests/test_isolated_provenance_archive.py` executes **real local bare Git + clone integration** without network or credentials: first append, replay, conflict, missing ref, invalid proof, two independent runs, main SHA invariance.

## Explicitly unresolved before production cutover

1. **No existing live workflow modification.** The incumbent `archive_provenance` and `archive` direct-main writers stay unchanged until an independently approved migration and canary plan. This research pilot cannot pass the #569 acceptance by itself.
2. **Read compatibility.** `forecast_provenance/`, `research_pairs/`, `history/`, and `evidence/settled.json` consumers currently read main. A future migration must add an authenticated, bounded, branch-specific read path and verify equivalent bytes on the public iPhone view, or explicitly declare a cutover break. Do not claim archive availability solely from an Actions artifact.
3. **Settlement cumulative merge.** Isolate `archive` separately; diagnose failing five `gh api -X PUT` retries with sanitized HTTP status and GitHub effective-branch/token conditions before attempting replacement. Never silently reset or overwrite forward-only settlements.
4. **Archive branch protections.** A dedicated archive ref must be initialized and protected by an authorized owner; it is not created in this change and is **not** a substitute for external immutable storage, independently trusted timestamping, or rights-holder provenance.
5. **No automatic promotion.** Existing proof bundle and `gh attestation` remain non-authoritative for real kickoff/result/source identity until independently authenticated. Legal data rights, actual prospective market feed, and out-of-sample EV remain blocked in #452.

## Acceptance roadmap
- [ ] Exact-head CI passes all `ops/tests`; reviewer examines use of `git ls-remote`, branch fixed ref, non-force push, worktree cleanup, collision behavior.
- [ ] Owner provisions fixed archive branch and no-main-write permissions with real GitHub controls, then only performs a synthetic pilot canary and verifies replay/collision on the real isolated ref.
- [ ] Audit and migrate downstream readers and the **other** `archive` / `settled.json` direct-main job. Maintain existing public report compatibility or an explicit HOLD marker.
- [ ] After independent human review and successful archival continuity canary, main RuleSet #439 can be activated and checked with zero bypass. Do not do this now.

**Original production remains HOLD/DISABLED.**
