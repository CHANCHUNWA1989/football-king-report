import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from archive_prepare import prepare

class ArchiveBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.snapshot=self.root/"snapshots"
        self.snapshot.mkdir()
        self.output=self.root/"repo"
        self.output.mkdir()
        for kind in ("asof","shadow","paired"):
            (self.snapshot/(kind+".json")).write_text(json.dumps({"kind":kind}))

    def run_prepare(self):
        return prepare(self.snapshot,self.output,"123","1",day="2026/10/09")

    def test_three_files_at_once(self):
        files=self.run_prepare()
        self.assertEqual(len(files),3)
        for rel in files:
            self.assertEqual(len(json.loads(gzip.decompress((self.output/rel).read_bytes()))),1)

    def test_optional_worldwide_shadow_snapshot_archived_immutably(self):
        (self.snapshot/"worldwide.json").write_text(json.dumps({
            "schema": "football-king-worldwide-uncalibrated-shadow-v1",
            "predictions": [], "production_recommendations": "DISABLED",
        }))
        files = self.run_prepare()
        self.assertEqual(len(files), 4)
        worldwide = [x for x in files if x.startswith("worldwide_shadow/")]
        self.assertEqual(len(worldwide), 1)
        self.assertEqual(
            json.loads(gzip.decompress((self.output/worldwide[0]).read_bytes()))[
                "production_recommendations"], "DISABLED")
        self.assertEqual(self.run_prepare(), [])
        (self.snapshot/"worldwide.json").write_text('{"changed":true}')
        with self.assertRaises(ValueError):
            self.run_prepare()

    def test_rerun_is_idempotent(self):
        self.run_prepare()
        self.assertEqual(self.run_prepare(),[])

    def test_differing_existing_archive_fails_closed(self):
        self.run_prepare()
        (self.snapshot/"shadow.json").write_text('{"kind":"changed"}')
        with self.assertRaises(ValueError):
            self.run_prepare()

    def test_invalid_id_rejected(self):
        with self.assertRaises(ValueError):
            prepare(self.snapshot,self.output,"../1","1",day="2026/10/09")

if __name__=="__main__":
    unittest.main()
