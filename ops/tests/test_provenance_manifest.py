import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from ops.provenance_manifest import build_manifest, write_manifest

def row():
    return dict(event_id="synthetic-1",competition="Synthetic",kickoff_at="2026-11-06T20:00:00+08:00",
                captured_at="2026-11-06T19:45:00+08:00",forecast_created_at="2026-11-06T19:30:00+08:00",
                bookmaker="TEST_ONLY",source_url="https://example.invalid/fixture",
                market="total",side="under",line="2.5",odds="1.87",home_goals=0,away_goals=0,
                model_version="synthetic",score_probabilities={"0-0":"0.6","1-1":"0.4"})

class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source=Path(self.tmp.name)/"synthetic.jsonl"
        self.source.write_text(json.dumps(row())+"\n",encoding="utf-8")
    def test_hash_matches_bytes(self):
        result=build_manifest(self.source)
        self.assertEqual(result["input_sha256"],hashlib.sha256(self.source.read_bytes()).hexdigest())
    def test_never_certifies(self):
        result=build_manifest(self.source)
        for key in ("source_authenticity_verified","model_provenance_verified","out_of_sample_verified","positive_ev_verified","production_recommendation_allowed"):
            self.assertFalse(result[key])
    def test_manifest_written(self):
        output=Path(self.tmp.name)/"manifest.json"
        write_manifest(self.source,output)
        self.assertEqual(json.loads(output.read_text())["coverage"]["snapshot_count"],1)
    def test_no_source_overwrite(self):
        before=self.source.read_bytes()
        with self.assertRaises(ValueError): write_manifest(self.source,self.source)
        self.assertEqual(self.source.read_bytes(),before)
    def test_changed_input_changes_digest(self):
        old=build_manifest(self.source)["input_sha256"]
        self.source.write_text(self.source.read_text()+"\n",encoding="utf-8")
        new=build_manifest(self.source)["input_sha256"]
        self.assertNotEqual(old,new)
    def test_invalid_data_rejected(self):
        self.source.write_text("not json",encoding="utf-8")
        with self.assertRaises(ValueError): build_manifest(self.source)

if __name__=="__main__":
    unittest.main()
