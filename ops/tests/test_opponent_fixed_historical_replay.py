"""Offline real-data regression. Fixed source blobs; no network or secrets.

Previously inspected 2025/26 archive, not an independent holdout or evidence
of full league coverage. Compare actual Python, not a second implementation.
"""
import json
import unittest
from pathlib import Path
from ops.opponent_adjusted_research import replay, metrics

EXPECTED = {
    "epl": (353,317,154,166),
    "championship": (521,484,219,222),
    "bundesliga": (294,261,142,145),
    "laliga": (365,334,177,179),
    "seriea": (344,310,166,170),
    "ligue1": (282,252,132,126),
}


class RealHistoricalReplayTest(unittest.TestCase):
    def test_fixed_six_league_python_replay(self):
        fixture=Path(__file__).parent/"fixtures"/"opponent_replay_2025_26.json"
        doc=json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(doc["season"],"2025-26")
        self.assertFalse(doc["source_completeness_certified"])
        self.assertEqual(set(s["league"] for s in doc["scopes"]),set(EXPECTED))
        self.assertEqual(len(doc["scopes"]),6)
        all_rows=[]
        report={}
        for scope in doc["scopes"]:
            league=scope["league"]
            n,paired,old_hits,new_hits=EXPECTED[league]
            self.assertEqual(len(scope["rows"]),n)
            records=[{"league":league,"date":d,"home":h,"away":a,
                      "score_ft":[gh,ga],"status":"FINISHED"}
                     for d,h,a,gh,ga in scope["rows"]]
            rows=replay(records,league)
            old,new=metrics(rows,"original"),metrics(rows,"candidate")
            self.assertEqual(len(rows),paired,league)
            self.assertEqual(old["hits"],old_hits,league)
            self.assertEqual(new["hits"],new_hits,league)
            report[league]={"original":old,"candidate":new}
            all_rows.extend(rows)
        old,new=metrics(all_rows,"original"),metrics(all_rows,"candidate")
        self.assertEqual(old["n"],1958)
        self.assertEqual(new["hits"],1008)
        self.assertEqual(old["hits"],990)
        self.assertAlmostEqual(old["log_loss"],1.0145297343943291,places=5)
        self.assertAlmostEqual(new["log_loss"],1.0014796116525408,places=5)
        self.assertAlmostEqual(old["brier"],.6077112287393215,places=5)
        self.assertAlmostEqual(new["brier"],.5982791268632528,places=5)
        print("OPPONENT_FIXED_HISTORICAL_REPLAY="+json.dumps({
            "original":old,"candidate":new,"leagues":report,
            "independent_forward_evidence":False,
            "production_recommendations":"DISABLED"},sort_keys=True))


if __name__=="__main__":
    unittest.main()
