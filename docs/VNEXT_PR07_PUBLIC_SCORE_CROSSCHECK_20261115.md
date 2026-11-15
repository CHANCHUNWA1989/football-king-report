# PR-07 — Public historical score cross-check (research, 2026-11-15)

**Fixture:** Bundesliga 2026/27 opening match, 28 Aug 2026 18:30 UTC:
FC Bayern München 5–1 VfB Stuttgart, 90 minutes. The previously inspected
OpenLigaDB match `83156` reported the same score. Its original local
response hash, previously observed but not externally publisher-attested:
`420aca223bdc71d3a5f88a0af8d76c54406567a296934a40bab313800b3e0e2d`.

## Public pages actually browsed on 2026-11-15

- **Official Bundesliga matchday:** https://www.bundesliga.com/en/bundesliga/matchday/2026-2027/1/fc-bayern-muenchen-vs-vfb-stuttgart/liveticker — FCB 5, VFB 1, FINAL.
- **Home club FC Bayern match report:** https://fcbayern.com/en/news/matchreports/2026/08/match-report-bundesliga-fc-bayern-v-vfb-stuttgart-280826 — expressly describes the 5–1 victory.
- **Away club VfB Stuttgart match data:** https://www.vfb.de/en/vfb/latest/news/professionals/2627/1-fc-bayern-muenchen----vfb-stuttgart-/ — match date 28 Aug 2026 and final 5–1.

**Finding:** three public publisher pages and the earlier OpenLigaDB response
claim the *same match and score*. This is a useful score cross-reference,
not proof they were produced from genuinely independent upstream feeds.

## Repeatable offline transcription check

`ops/research_manifests/openligadb_83156_public_score_crosscheck_20261115.json`
contains ONLY pinned URLs, fixture/score metadata and explicitly **unattested**
researcher transcriptions. It contains no protected raw web pages or provider
response JSON.

`ops/vnext_public_score_crosscheck.py` checks source list, known HTTPS URLs,
home/away identity, date, final score, static OpenLigaDB digest and
fail-closed flags. No HTTP call is made; no website is re-read by the CLI.
`ops/tests/test_vnext_public_score_crosscheck.py` checks adversarial synthetic
changes (URL spoof, duplicate publisher, changed score/teams/date, fake trust
claims, wrong digest, malformed JSON).

Run manually:

    python -m ops.vnext_public_score_crosscheck --manifest ops/research_manifests/openligadb_83156_public_score_crosscheck_20261115.json

Exit 0 means only that the **transcribed metadata** is internally
consistent. It does NOT authenticate any external source page.

## Critical unresolved evidence

- No original cryptographically publisher-signed HTML/HTTP response or
  trustworthy independently attested capture timestamp.
- No audit establishing upstream independence of the official club, league
  or OpenLigaDB score feeds. Separate domains alone are insufficient.
- No licensed, sealed, matched PRE-KICKOFF forecast for this historical fixture.
- No validated new model performance, certified prospective result sample,
  independently approved data-rights integration, tradeable market quote or EV.
- `main` branch protection and current-head independent human review remain
  blocked: https://github.com/CHANCHUNWA1989/football-king-report/issues/439

Keep PR #436 **OPEN / DRAFT / UNMERGED**. Always **HOLD / DISABLED**.
`certified_prospective_samples=0`; `positive_ev_verified=false`.
No modification to `main`, archive rows, scheduled collection or production.
