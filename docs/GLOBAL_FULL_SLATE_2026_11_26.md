# Global Full-Slate Ledger — phase 1 (2026-11-26)
The existing global league catalogue and shortlist do not enumerate every rejected observation. This addition is a read-only coverage ledger, not a replacement forecasting engine. It consumes the existing public report and bounded worldwide input, preserves missing/invalid/out-of-window observations and lists HOLD for all markets. Counts refer to observations, not unique worldwide fixtures; exact duplicate observations from the same source/native identity are counted separately. Cross-publisher names are not treated as attested identity. No raw prices, extra API requests, model retraining, production promotion or historical rewrite.

Window: current Hong Kong calendar day plus next day; outside-window rows remain visible with reason. Core model references require exact source event ID, league, teams and kickoff plus valid clocks; this is not independently attested identity or probability calibration. Worldwide model references intentionally not joined until native identity mapping is verified. Missing provider inputs and bounded omissions are explicit. The output is JSON only in this phase; mobile interface and live event acquisition remain separate work.

Run: python -m ops.global_full_slate --site app/site --worldwide-input PATH
Test: python -m unittest discover -s ops/tests -p test_global_full_slate.py -v
Acceptance: input accounting balances, duplicates do not inflate retained rows, stale or ambiguous data never promotes, no production output. CI and real data run must be independently verified before merge.
