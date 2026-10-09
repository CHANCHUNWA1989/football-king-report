"""The new free sources must appear on iPhone as research-only information."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from free_extension_overlay import build
from research_extensions import collect, CATALOG


class Body:
    def __init__(self, content):
        import json
        self.bytes=json.dumps(content).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.bytes[:n]


class SiteOverlayTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        def requester(req,timeout):
            if req.full_url!=CATALOG:
                raise RuntimeError("unexpected network")
            return Body([{"competition_id":9,"season_id":281,"competition_name":"Bundesliga"}])
        self.audit=collect(now=self.now,keys={},requester=requester)

    def test_actual_free_statsbomb_catalog_is_research_only(self):
        status=build(self.audit,now=self.now+timedelta(minutes=2))
        self.assertEqual(status["status"],"RESEARCH_ONLY")
        self.assertEqual([p["provider"] for p in status["providers"]],
                         ["openfootapi","statsbomb_open_data"])
        self.assertEqual(status["providers"][0]["status"],"NOT_CONFIGURED")
        self.assertEqual(status["providers"][1]["catalogue_entries"],1)
        self.assertFalse(status["used_to_promote_model"])
        self.assertTrue(status["historical_data_only_cannot_validate_current_season"])

    def test_unknown_or_modified_provider_does_not_pass(self):
        self.audit["current_free_odds_1x2_confirmed"]=True
        r=build(self.audit,now=self.now)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["reason"],"SOURCE_CATALOG_INVALID")

    def test_stale_catalog_never_claims_live_coverage(self):
        r=build(self.audit,now=self.now+timedelta(hours=40))
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["reason"],"SOURCE_CATALOG_STALE")


if __name__=="__main__":
    unittest.main()
