import gzip
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from ops import long_horizon_shadow_inventory as mod


class LongHorizonInventoryTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,28,12,tzinfo=timezone.utc)
        self.row={"league":"epl","event_id":"fixture-a","home":"Everton","away":"Arsenal",
                  "kickoff_utc":"2026-11-28T20:00:00+00:00",
                  "candidate_prediction_utc":"2026-11-27T10:00:00+00:00"}

    def write(self,root,day,run,rows):
        folder=Path(root)/day.strftime("%Y/%m/%d")
        folder.mkdir(parents=True,exist_ok=True)
        with gzip.open(folder/f"{run}-1.json.gz","wb") as f:
            f.write(json.dumps({"rows":rows}).encode())

    def test_repeated_captures_do_not_inflate_coverage(self):
        with tempfile.TemporaryDirectory() as root:
            day=self.now.date()-timedelta(days=1)
            self.write(root,day,1,[self.row])
            self.write(root,day,2,[self.row])
            with patch.object(mod,"candidates",side_effect=lambda d:d["rows"]),patch.object(mod,"dc_candidates",return_value=[]),patch.object(mod,"matching_dc",return_value={"same":True}):
                r=mod.inventory(root,self.now)
            self.assertEqual(r["scan_counts"]["candidate_observations"],2)
            self.assertEqual(r["unique_fixture_count"],1)
            self.assertEqual(r["three_model_ready"],1)
            self.assertEqual(r["authenticated_forward_samples"],0)
            self.assertEqual(r["elapsed_recorded_kickoff_weeks"],[])
            self.assertFalse(r["archive_history_complete"])

    def test_conflicting_fixture_binding_and_file_budget(self):
        with tempfile.TemporaryDirectory() as root:
            day=self.now.date()-timedelta(days=1)
            other=dict(self.row,away="Chelsea")
            self.write(root,day,1,[self.row,other])
            self.write(root,day,2,[self.row,other])
            with patch.object(mod,"MAX_FILES",1),patch.object(mod,"candidates",side_effect=lambda d:d["rows"]),patch.object(mod,"dc_candidates",return_value=[]),patch.object(mod,"matching_dc",return_value={"same":True}):
                r=mod.inventory(root,self.now)
            self.assertTrue(r["budget_limit_reached"])
            self.assertEqual(r["unique_fixture_count"],2)
            self.assertEqual(r["three_model_ready"],0)
            self.assertEqual(r["by_league"]["epl"]["identity_conflicts"],2)
            self.assertEqual(r["production_recommendations"],"DISABLED")


if __name__=="__main__":
    unittest.main()
