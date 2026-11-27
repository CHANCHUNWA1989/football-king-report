import json
import unittest
from datetime import datetime,timezone
from pathlib import Path
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.research_missing_fixture_discovery_v16 import candidates
from ops.research_supplemental_history_v32 import inventory
from ops.research_calendar_gap_priority_v33 import selectors,from_root

NOW="2026-11-02T00:00:00Z"
class CalendarGapTests(unittest.TestCase):
    def test_gap_detail_does_not_inflate_counts(self):
        raw,p=fixture()
        baseline=inventory(raw,[("p",encode(p))],[],as_of=NOW)
        full=inventory(raw,[("p",encode(p))],[],as_of=NOW,include_gap_detail=True)
        self.assertEqual(baseline["scenarios"],full["scenarios"])
        self.assertEqual(full["gap_detail"]["teams_with_shortage"],2)
        self.assertEqual(full["gap_detail"]["by_league"]["bundesliga"]["team_history_shortage"],1)
        self.assertFalse(full["gap_detail"]["distinct_missing_matches_inferred"])
        self.assertEqual(full["gap_detail"]["team_priorities"][0]["max_prior_match_deficit"],3)
    def test_calendar_selectors_do_not_modify_original(self):
        raw,_=fixture();rows=candidates(raw);before=dict(rows)
        selected,missing=selectors(rows,primary=True)
        self.assertEqual(rows,before)
        self.assertEqual(missing,[])
        self.assertEqual(selected,rows)
    def test_earlier_forecast_calendar_gap(self):
        raw,_=fixture();rows=candidates(raw)
        key=next(iter(rows));rows[key]=dict(rows[key],forecast_utc="2026-10-30T14:00:00Z")
        selected,missing=selectors(rows,primary=True)
        # A single forecast defines a one-day forecast interval; kickoff
        # does not extend its end (the archive readers already cover kickoff).
        self.assertEqual(missing,["2026-10-30"])
        self.assertEqual(len(selected),2)
    def test_multiple_forecasts_include_intervening_gap(self):
        rows={
            ("bundesliga","a"):{"forecast_utc":"2026-10-30T14:00:00Z",
                                "kickoff_utc":"2026-11-01T15:00:00Z"},
            ("bundesliga","b"):{"forecast_utc":"2026-11-01T10:00:00Z",
                                "kickoff_utc":"2026-11-02T15:00:00Z"},
        }
        for primary in (True,False):
            with self.subTest(primary=primary):
                selected,missing=selectors(rows,primary=primary)
                self.assertEqual(missing,["2026-10-30","2026-10-31"])
                self.assertEqual(len(selected),4)
                self.assertEqual(len(rows),2)
    def test_excessive_calendar_span_rejected(self):
        raw,_=fixture();rows=candidates(raw)
        key=next(iter(rows));rows[key]=dict(rows[key],forecast_utc="2026-01-01T14:00:00Z")
        # Force a second forecast clock outside the bounded span.
        rows["second"]=dict(rows[key],forecast_utc="2026-11-01T14:00:00Z")
        with self.assertRaises(ValueError):selectors(rows,primary=True)
    def test_actual_archives(self):
        root=Path(__file__).resolve().parents[2];ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(raw,ledger.read_bytes())
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["training_admission"])
        inv=r["inventory"];g=inv["gap_detail"]
        self.assertEqual(sum(x["targets"] for x in g["by_league"].values()),inv["forecast_target_count"])
        self.assertEqual(sum(x["all_three_thresholds"] for x in g["by_league"].values()),
                         inv["scenarios"]["24"]["expanded"]["all_three_thresholds"])
        # Report only the highest priority 12 teams in CI output.
        compact={**r,"inventory":{**inv,"gap_detail":{**g,"team_priorities":g["team_priorities"][:12]}}}
        print("V33_CALENDAR_GAP_SUMMARY "+json.dumps(compact,sort_keys=True))
