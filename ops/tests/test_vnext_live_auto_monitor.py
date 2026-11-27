import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vnext_live_auto_monitor import inspect, monitor, SOURCES
NOW=datetime(2026,11,25,10,tzinfo=timezone.utc)
def sample(age=0,status="RESEARCH_ONLY"):
    return {"schema":"s","status":status,"ts":(NOW-timedelta(seconds=age)).isoformat(),
            "production_recommendations":"DISABLED"}
class MonitorTests(unittest.TestCase):
    def test_fresh_only_metadata(self):
        self.assertEqual(inspect(sample(),"s","ts",60,NOW),"RECENT_RESEARCH_METADATA_ONLY")
    def test_stale_future_unconfigured(self):
        for doc,reason in [(sample(61),"STALE_METADATA"),(sample(-1),"FUTURE_METADATA"),
                           (sample(status="NOT_CONFIGURED"),"NOT_CONFIGURED")]:
            self.assertEqual(inspect(doc,"s","ts",60,NOW),reason)
    def test_wrong_schema_and_safety(self):
        self.assertEqual(inspect(sample(),"x","ts",60,NOW),"INVALID_METADATA")
        d=sample(); d["production_recommendations"]="ENABLED"
        self.assertEqual(inspect(d,"s","ts",60,NOW),"INVALID_METADATA")
    def test_missing_and_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            out=monitor(root,NOW)
            self.assertTrue(all(v=="MISSING_METADATA" for v in out["source_metadata_status"].values()))
            path=root / SOURCES["hkjc_third_party"][0]
            path.parent.mkdir()
            path.write_text('{"status":1,"status":2}')
            self.assertEqual(monitor(root,NOW)["source_metadata_status"]["hkjc_third_party"],"INVALID_METADATA")
            self.assertFalse(out["actual_live_odds_verified"])
            self.assertEqual(out["provider_calls"],0)
            self.assertEqual(out["production_recommendations"],"DISABLED")
