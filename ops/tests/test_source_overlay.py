"""Free provider overlays must not be converted into betting signals or 1X2 odds."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source_overlay import build
from secondary_sources import collect

NOW = datetime.now(timezone.utc)


class Response:
    def __init__(self, body):
        import json
        self.raw=json.dumps(body).encode()
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def read(self,length):
        return self.raw[:length]


def fake(req,timeout):
    league=int(req.full_url.split("id=")[-1])
    return Response({"events":[{
        "idEvent":str(league), "idLeague":str(league),
        "strHomeTeam":"Bayern München" if league==4331 else "Arsenal",
        "strAwayTeam":"Borussia Dortmund" if league==4331 else "Chelsea",
        "strTimestamp":(NOW+timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S"),
        "strStatus":"NS"}]})


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.shadow={"status":"SHADOW_ONLY","production_recommendations":"DISABLED",
                     "predictions":[{"league":"bundesliga","home":"Bayern Munich",
                                     "away":"Borussia Dortmund",
                                     "kickoff_utc":(NOW+timedelta(days=2)).isoformat()}]}
        self.audit=collect(now=NOW,keys={},requester=fake)

    def test_valid_free_source_6x_and_match(self):
        report=build(self.shadow,self.audit,now=datetime.now(timezone.utc))
        self.assertEqual(report["status"],"RESEARCH_ONLY")
        self.assertEqual(len(report["providers"]),4)
        self.assertEqual(report["matched_kickoff_agreements"],1)
        self.assertFalse(report["source_samples_used_as_forecast_training"])
        self.assertFalse(report["can_replace_market_1x2"])

    def test_missing_snapshot_hold_with_four_providers(self):
        report=build(self.shadow,None,now=NOW)
        self.assertEqual(report["status"],"HOLD")
        self.assertEqual(len(report["providers"]),4)
        self.assertTrue(all(p["status"]=="NOT_YET_COLLECTED" for p in report["providers"]))

    def test_mismatched_kickoff_never_qualifies(self):
        self.shadow["predictions"][0]["kickoff_utc"]=(NOW+timedelta(days=2,hours=3)).isoformat()
        result=build(self.shadow,self.audit,now=datetime.now(timezone.utc))
        self.assertEqual(result["matched_kickoff_agreements"],0)
        self.assertEqual(result["kickoff_disagreements_needing_review"],1)

    def test_expired_snapshot_hold(self):
        old=datetime.now(timezone.utc)+timedelta(hours=40)
        report=build(self.shadow,self.audit,now=old)
        self.assertEqual(report["status"],"HOLD")
        self.assertEqual(report["reason"],"EXTERNAL_SOURCE_SNAPSHOT_STALE_OR_FUTURE")

    def test_no_provider_can_authorize_betting(self):
        self.audit["production_recommendations"]="ENABLED"
        r=build(self.shadow,self.audit,now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")


if __name__=="__main__":
    unittest.main()
