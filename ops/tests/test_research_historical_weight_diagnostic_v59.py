import json
import unittest
from datetime import datetime,timedelta,timezone
from ops.research_historical_weight_diagnostic_v59 import evaluate

CUT="2026-11-01T00:00:00+00:00"

def ledger():
    cut=datetime.fromisoformat(CUT)
    rows=[]
    for i in range(65):
        k=cut+timedelta(days=i-42,hours=12)
        f=k-timedelta(hours=2)
        rows.append(dict(key=json.dumps(["epl","home"+str(i),"away",k.isoformat()]),
            league="epl",kickoff_utc=k.isoformat(),forecast_utc=f.isoformat(),
            market_utc=(f-timedelta(minutes=1)).isoformat(),
            y=0,p=[.8,.1,.1],m=[.4,.3,.3],
            production_recommendations="DISABLED",
            fixture_result_source_independently_verified=False))
    return dict(schema="football-king-forward-research-1",n=len(rows),samples=rows,
        checked_utc=(cut+timedelta(days=30)).isoformat(),
        production_recommendations="DISABLED",results_independently_verified=False)

def run(d):
    return evaluate(json.dumps(d).encode(),cutoff=CUT)

class HistoricalWeightDiagnosticV59(unittest.TestCase):
    def test_split_and_fit(self):
        r=run(ledger())
        self.assertTrue(r["diagnostic_completed"])
        self.assertEqual((r["train_n"],r["test_n"],r["excluded_n"]),(35,23,7))
        self.assertEqual(r["diagnostic_policy"]["model_weight"],1.)
        self.assertLess(r["test_metrics"]["blend"]["brier"],r["test_metrics"]["market"]["brier"])
    def test_test_outcome_cannot_change_policy(self):
        d=ledger()
        a=run(d)
        for row in d["samples"][42:]:
            row["y"]=2
        b=run(d)
        self.assertEqual(a["diagnostic_policy"],b["diagnostic_policy"])
        self.assertNotEqual(a["test_metrics"],b["test_metrics"])
    def test_ties_favor_market(self):
        d=ledger()
        for row in d["samples"]:
            row["p"]=row["m"][:]
        self.assertEqual(run(d)["diagnostic_policy"]["model_weight"],0.)
    def test_no_promotion(self):
        r=run(ledger())
        for k in ("training_admission","qualified_for_production","independent_oos_proven",
                  "outcome_availability_proven","production_weights_fitted","test_used_for_weight_selection"):
            self.assertIs(r[k],False)
        self.assertEqual(r["authenticated_samples"],0)
    def test_insufficient(self):
        d=ledger();d["samples"]=d["samples"][:3];d["n"]=3
        r=run(d)
        self.assertFalse(r["diagnostic_completed"])
        self.assertNotIn("test_metrics",r)
    def test_invalid(self):
        d=ledger();d["samples"][0]["market_utc"]=d["samples"][0]["kickoff_utc"]
        self.assertFalse(run(d)["diagnostic_completed"])
