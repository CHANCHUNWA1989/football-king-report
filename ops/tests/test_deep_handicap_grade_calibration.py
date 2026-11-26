"""Synthetic descriptive calibration regression tests."""
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_forward_evaluation import evaluate
from deep_handicap_grade_calibration import _bins
from test_deep_handicap_forward_evaluation import row

NOW="2026-06-01T00:00:00Z"


def cohort(n=120):
    rows=[]
    start=datetime(2026,1,5,12,tzinfo=timezone.utc)
    for j in range(n):
        r=row(f"cal-{j}")
        ko=start+timedelta(weeks=j%12,minutes=j)
        cutoff=(ko-timedelta(minutes=30)).isoformat()
        r.update(kickoff_utc=ko.isoformat(),information_cutoff_utc=cutoff)
        for name in ("baseline","challenger"):
            r[name].update(kickoff_utc=ko.isoformat(),information_cutoff_utc=cutoff,
                           recorded_utc=(ko-timedelta(minutes=25)).isoformat())
        for obs in r["results"]:
            obs.update(kickoff_utc=ko.isoformat(),captured_utc=(ko+timedelta(hours=2)).isoformat(),
                       score_ft=[3,0] if j%2==0 else [1,0])
        rows.append(r)
    return rows


def diag(rows,kind="SYNTHETIC"):
    return evaluate(rows,as_of_utc=NOW)["cohorts"][kind]["stratified_grade_calibration"]


class GradeCalibrationTests(unittest.TestCase):
    def test_known_synthetic_gaps_and_impossible_grades(self):
        d=diag(cohort())
        g=d["groups"][0]
        self.assertEqual(g["status"],"DESCRIPTIVE_ONLY")
        m=g["models"]["challenger"]
        self.assertAlmostEqual(m["by_grade"]["FULL_WIN"]["signed_gap"],.1)
        self.assertAlmostEqual(m["by_grade"]["FULL_WIN"]["ece"],.1)
        self.assertAlmostEqual(m["top_grade"]["signed_confidence_gap"],.1)
        for name in ("PUSH","HALF_WIN"):
            self.assertEqual(m["by_grade"][name]["status"],"STRUCTURALLY_IMPOSSIBLE_FOR_LINE")
        self.assertFalse(d["calibration_verified"])
        self.assertFalse(d["recalibration_applied"])
        self.assertFalse(d["source_authenticated"])

    def test_small_cohorts_and_mixed_versions(self):
        rows=cohort()
        for r in rows[:60]:
            r["challenger"]["model_id"]="different-version"
        d=diag(rows)
        self.assertEqual(len(d["groups"]),2)
        self.assertTrue(all(g["models"] is None for g in d["groups"]))
        self.assertEqual(diag([])["groups"],[])
        self.assertIsNone(diag(cohort(10))["groups"][0]["models"])

    def test_sparse_bin_does_not_report_partial_ece(self):
        b=_bins([(0.5,True)]*20+[(1.0,False)])
        self.assertEqual(b["covered_count"],20)
        self.assertIsNone(b["ece"])
        self.assertIsNone(b["bins"][9]["signed_gap"])
        self.assertAlmostEqual(_bins([(1.0,False)]*20)["ece"],1)

    def test_league_line_and_data_kind_separation(self):
        rows=cohort()
        for r in rows[:40]:
            r["data_kind"]="EXTERNAL_UNAUTHENTICATED"
        for r in rows[40:80]:
            for obj in (r,r["baseline"],r["challenger"],*r["results"]):
                obj["league_id"]="other"
        for r in rows[80:]:
            for obj in (r,r["baseline"],r["challenger"]):
                obj["handicap"]=-2.5
            for name in ("baseline","challenger"):
                p=r[name]["probabilities"]
                p["FULL_LOSS"]+=p["HALF_LOSS"]
                p["HALF_LOSS"]=0
        a=diag(rows)
        b=diag(rows,"EXTERNAL_UNAUTHENTICATED")
        self.assertEqual(sorted(g["n"] for g in a["groups"]),[40,40])
        self.assertEqual(b["groups"][0]["n"],40)
        self.assertTrue(all(g["models"] is None for g in a["groups"]+b["groups"]))
