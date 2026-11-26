# StatsBomb historical event replay

Research-only parser: ops/live_core_statsbomb_event_replay.py. Use audit(raw,
expected_blob, home_id, away_id) with authorized private captured bytes.
The expected Git blob digest must be taken from the source; it is an integrity
check, not authentication. Do not commit or publish source event data or derived
research without satisfying the provider agreement and attribution requirements.
Source: StatsBomb Open Data, https://github.com/hudl/open-data .
Terms and attribution: https://github.com/hudl/open-data/blob/master/README.md .
No StatsBomb data, derived statistics, or external download workflow are
included in this PR. Existing combined CI exercises synthetic fixtures only.

Dismissal exposure is measured using period-relative elapsed milliseconds,
including stoppage, not ball-in-play duration. Exclude extra time and shootouts.
Use starting XI and substitutions to reject ambiguous non-roster dismissals;
temporary player exits do not modify the permanent-dismissal count. Reject
duplicate incidents, missing xG, time regressions and incomplete periods.
Only observed shot xG is summed; own goals are not modeled as shot xG.
This parser does not fit red-card coefficients or update the live model.
Historical event timestamps are not proof of real-time data availability.
A future fixed, non-selected cohort with independent temporal holdout and
adequate red-card exposure across minutes/score states is required before
calibration; control for baseline team strength and score state, and report
uncertainty. No causal, live, EV or production qualification is permitted.
