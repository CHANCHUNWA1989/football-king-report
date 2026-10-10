"""Pages J1 free market panel may display status only, never raw price."""
import json
import sys
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from japan_free_market import collect
from japan_market_overlay import publish


class JapanMarketOverlayTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,10,13,0,tzinfo=timezone.utc)

    def test_missing_source_never_breaks_iphone_site(self):
        with tempfile.TemporaryDirectory() as root:
            out=publish(root,Path(root)/"missing.json",now=self.now)
            self.assertEqual(out["status"],"HOLD")
            self.assertTrue(out["source_metadata_unavailable_or_stale"])
            self.assertFalse(out["public_market_prices_or_recommendations_available"])
            self.assertFalse(out["site_inplay_odds_verified"])
            self.assertEqual(out["bet_recommendation_count"],0)
            self.assertTrue((Path(root)/"japan_free_market.json").is_file())

    def test_sanitized_existing_j1_status_available_only_as_research(self):
        doc=collect({},now=self.now)
        state=doc["j1_free_prematch_sources"][2]
        state.update(configured=True,status="RESEARCH_ONLY",
                     reason="DERIVED_PREMATCH_3WAY_CONSENSUS_ONLY",
                     requests_attempted=2,upcoming_events=5,
                     fresh_3way_event_count=5)
        doc["status"]="RESEARCH_ONLY"
        with tempfile.TemporaryDirectory() as root:
            input_file=Path(root)/"in.json"
            input_file.write_text(json.dumps(doc),encoding="utf-8")
            out=publish(root,input_file,now=self.now)
            self.assertFalse(out["source_metadata_unavailable_or_stale"])
            self.assertEqual(out["j1_free_prematch_sources"][2][
                "fresh_3way_event_count"],5)
            self.assertFalse(out["public_market_prices_or_recommendations_available"])
            self.assertEqual(out["production_recommendations"],"DISABLED")

    def test_outdated_and_suspicious_raw_odds_fall_back_to_hold(self):
        for invalid in ("stale","raw_quote"):
            doc=collect({},now=self.now)
            if invalid=="stale":
                doc["collected_utc"]=(self.now-timedelta(days=4)).isoformat()
            else:
                doc["raw_bookmaker_quotes"]=[{"price":2.25}]
            with tempfile.TemporaryDirectory() as root:
                p=Path(root)/"in.json"
                p.write_text(json.dumps(doc),encoding="utf-8")
                out=publish(root,p,now=self.now)
                self.assertTrue(out["source_metadata_unavailable_or_stale"])
                self.assertEqual(out["status"],"HOLD")
                self.assertEqual(out["bet_recommendation_count"],0)


if __name__=="__main__":
    unittest.main()
