"""Fresh independent fixture time contradictions suspend current suggestions."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture_consensus import build
from secondary_sources import SD_BD, collect

NOW = datetime.now(timezone.utc).replace(microsecond=0)
KICKOFF = NOW + timedelta(days=2)


class Body:
    def __init__(self, document):
        import json
        self.body=json.dumps(document).encode("utf-8")
    def read(self, count):return self.body[:count]
    def __enter__(self):return self
    def __exit__(self,*args):pass


def source_clock(req, timeout, shift_minutes=0):
    ident=int(req.full_url.split("id=")[-1])
    return Body({"events":[{
        "idEvent":str(ident), "idLeague":str(ident),
        "strHomeTeam":"Bayern München" if ident==SD_BD["bundesliga"] else "Arsenal",
        "strAwayTeam":"Borussia Dortmund" if ident==SD_BD["bundesliga"] else "Chelsea",
        "strTimestamp":(KICKOFF+timedelta(minutes=shift_minutes)).isoformat(),
        "strStatus":"NS"
    }]})


class ConsensusTests(unittest.TestCase):
    def setUp(self):
        self.shadow={
            "status":"SHADOW_ONLY","production_recommendations":"DISABLED",
            "predictions":[{
                "league":"bundesliga","home":"Bayern Munich",
                "away":"Borussia Dortmund","kickoff_utc":KICKOFF.isoformat(),
                "prediction_utc":NOW.isoformat(), "production_recommendations":"DISABLED"
            }]
        }

    def audit(self, shift_minutes=0):
        return collect(now=NOW,keys={},requester=lambda req,timeout:
                       source_clock(req,timeout,shift_minutes))

    def test_time_agreement_from_independent_provider(self):
        result=build(self.shadow,self.audit(),now=NOW+timedelta(minutes=1))
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertGreaterEqual(result["independent_kickoff_agreement_observations"],1)
        self.assertEqual(result["affected_fixtures"],0)
        self.assertFalse(result["disagreements"])
        self.assertFalse(result["no_independent_result_verification_claim"] is False)

    def test_date_disagreement_detected_for_same_league_and_clubs(self):
        result=build(self.shadow,self.audit(120),now=NOW+timedelta(minutes=1))
        self.assertEqual(result["affected_fixtures"],1)
        self.assertGreater(result["conflicting_kickoff_observations"],0)
        self.assertEqual(result["disagreements"][0]["provider"],"thesportsdb")
        self.assertEqual(result["disagreements"][0]["action"],
                         "SUSPEND_RESEARCH_SELECTION_PENDING_SCHEDULE_REVIEW")
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_other_league_never_confused(self):
        self.shadow["predictions"][0]["league"]="epl"
        result=build(self.shadow,self.audit(120),now=NOW+timedelta(minutes=1))
        self.assertEqual(result["affected_fixtures"],0)

    def test_other_club_never_confused(self):
        self.shadow["predictions"][0]["away"]="Schalke 04"
        result=build(self.shadow,self.audit(120),now=NOW+timedelta(minutes=1))
        self.assertEqual(result["affected_fixtures"],0)

    def test_stale_vendor_cannot_override_new_model(self):
        result=build(self.shadow,self.audit(120),now=NOW+timedelta(hours=39))
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["affected_fixtures"],0)
        self.assertEqual(result["provider_freshness"]["secondary"],"STALE")

    def test_missing_source_is_not_called_verified(self):
        result=build(self.shadow,{},now=NOW)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["affected_fixtures"],0)
        self.assertTrue(result["source_accuracy_not_proven"])

    def test_invalid_forecast_never_create_agreement(self):
        self.shadow["status"]="HOLD"
        result=build(self.shadow,self.audit(),now=NOW)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["inspected_shadow_fixtures"],0)

    def test_openligadb_provenance_is_independent_from_secondary(self):
        fake_wide={"collected_utc":NOW.isoformat(),
                   "league_coverage":[{
                     "league":"bundesliga","provider":"openligadb",
                     "access_status":"FETCHED","sample":[{
                        "provider_event_id":"123","league":"bundesliga",
                        "home":"Bayern München","away":"Borussia Dortmund",
                        "kickoff_utc":(KICKOFF+timedelta(hours=3)).isoformat(),
                        "status":"SCHEDULED","source":"openligadb"
                     }]
                   }]}
        with patch("fixture_consensus.verify_wide",return_value=NOW):
            result=build(self.shadow,None,fake_wide,now=NOW)
        self.assertEqual(result["provider_freshness"]["openligadb"],"VALID_WINDOW")
        self.assertEqual(result["affected_fixtures"],1)


if __name__=="__main__":
    unittest.main()
