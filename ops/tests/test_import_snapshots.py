import json
import tempfile
import unittest
from pathlib import Path
from ops.import_snapshots import import_jsonl

def record(i=1):
    return dict(event_id=f"synthetic-{i}",competition="Synthetic",kickoff_at="2026-11-06T20:00:00+08:00",
                captured_at="2026-11-06T19:45:00+08:00",forecast_created_at="2026-11-06T19:30:00+08:00",
                bookmaker="TEST_ONLY",source_url="https://example.invalid/fixture",
                market="total",side="under",line="2.5",odds="1.87",home_goals=0,away_goals=0,
                model_version="synthetic",score_probabilities={"0-0":"0.6","1-1":"0.4"})

class ImportTests(unittest.TestCase):
    def run_input(self, text, **kwargs):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"data.jsonl"
            path.write_text(text,encoding="utf-8")
            return import_jsonl(path,**kwargs)
    def test_one_row(self):
        report=self.run_input(json.dumps(record())+"\n")
        self.assertEqual(report["snapshot_count"],1)
        self.assertFalse(report["positive_ev_verified"])
    def test_two_rows(self):
        report=self.run_input("\n".join(json.dumps(record(i)) for i in (1,2)))
        self.assertEqual(report["unique_event_count"],2)
    def test_invalid_json(self):
        with self.assertRaises(ValueError): self.run_input("{oops")
    def test_nonobject_json(self):
        with self.assertRaises(ValueError): self.run_input("[]")
    def test_empty_rejected(self):
        with self.assertRaises(ValueError): self.run_input("\n\n")
    def test_duplicate_rejected(self):
        row=json.dumps(record())
        with self.assertRaises(ValueError): self.run_input(row+"\n"+row)
    def test_row_limit(self):
        with self.assertRaises(ValueError): self.run_input(json.dumps(record())+"\n",max_rows=0)
    def test_nonfinite_json_rejected(self):
        row=json.dumps(record()).replace('"odds": "1.87"','"odds": NaN')
        with self.assertRaises(ValueError): self.run_input(row)

if __name__=="__main__":
    unittest.main()
