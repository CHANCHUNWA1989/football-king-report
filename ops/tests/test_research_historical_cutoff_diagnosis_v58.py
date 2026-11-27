import json
import unittest
from ops.research_historical_cutoff_diagnosis_v58 import diagnose

def ledger():
    rows=[]
    for i in range(3):
        day=10+i
        k=f"2026-10-{day}T18:00:00+00:00"
        f=f"2026-10-{day}T17:00:00+00:00"
        m=f"2026-10-{day}T"+("16:56" if i==0 else "15:00")+":00+00:00"
        rows.append(dict(key=json.dumps(["epl","home"+str(i),"away",k]),
            league="epl",kickoff_utc=k,forecast_utc=f,market_utc=m,
            y=0,p=[.6,.2,.2],m=[.5,.25,.25],score_ft=[1,0],
            source_fixture_identity={"source":"synthetic"},
            production_recommendations="DISABLED",
            fixture_result_source_independently_verified=False))
    return dict(schema="football-king-forward-research-1",n=len(rows),samples=rows,
        checked_utc="2026-10-14T00:00:00+00:00",production_recommendations="DISABLED",
        results_independently_verified=False)

def run(d):
    return diagnose(json.dumps(d).encode())

class HistoricalCutoffDiagnosisV58(unittest.TestCase):
    def test_cohorts_and_loss(self):
        r=run(ledger())
        self.assertTrue(r["diagnosis_completed"])
        self.assertEqual(r["cohorts"]["all"]["n"],3)
        self.assertEqual(r["cohorts"]["age_le_300"]["n"],1)
        self.assertEqual(r["cohorts"]["age_le_3600"]["n"],1)
        self.assertEqual(r["cohorts"]["age_le_21600"]["n"],3)
        self.assertAlmostEqual(r["cohorts"]["all"]["delta_brier"],-.135)
        self.assertTrue(all(abs(x+.135)<1e-10 for x in r["cohorts"]["all"]["leave_one_day_out_delta_brier"]))
        self.assertIsNone(r["cohorts"]["age_le_300"]["leave_one_day_out_delta_brier"])
    def test_no_promotion_even_when_better(self):
        r=run(ledger())
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["qualified_for_production"])
        self.assertFalse(r["independent_oos_proven"])
        self.assertFalse(r["weights_fitted"])
    def test_score_conflict(self):
        d=ledger()
        d["samples"][0]["score_ft"]=[0,1]
        r=run(d)
        self.assertFalse(r["diagnosis_completed"])
        self.assertNotIn("cohorts",r)
    def test_missing_provenance(self):
        d=ledger()
        del d["samples"][0]["score_ft"]
        del d["samples"][0]["source_fixture_identity"]
        r=run(d)
        self.assertEqual(r["missing_exact_score"],1)
        self.assertEqual(r["missing_source_identity"],1)
    def test_leakage(self):
        d=ledger()
        d["samples"][0]["market_utc"]=d["samples"][0]["kickoff_utc"]
        self.assertFalse(run(d)["diagnosis_completed"])
    def test_empty(self):
        d=ledger()
        d.update(samples=[],n=0)
        self.assertEqual(run(d)["cohorts"]["all"],{"n":0})
