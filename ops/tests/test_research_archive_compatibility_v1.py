import unittest
import tempfile
from pathlib import Path
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_model_source_binding_v1 import MODEL_FILES,freeze_versioned_pricing_evidence
from ops.research_archive_compatibility_v1 import assess_archive_compatibility

class ArchiveCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
        self.quotes=[]
        for market,selection,line in (
            ("handicap","home",-0.25),("handicap","away",-0.25),
            ("totals","over",2.5),("totals","under",2.5)):
            for source,upstream in (("a","up-a"),("b","up-b")):
                self.quotes.append(Quote(source=source,upstream_provider=upstream,
                    bookmaker="book-a",event_id="fixture",market=market,
                    selection=selection,line=line,decimal_odds=1.91,
                    observed_at=self.now-timedelta(seconds=20),
                    kickoff_at=self.now+timedelta(hours=1)))
    def freeze(self,root="."):
        return freeze_versioned_pricing_evidence(root=root,event_id="fixture",
            home_xg=1.5,away_xg=1.1,quotes=self.quotes,now=self.now,
            handicap_line=-0.25,totals_line=2.5)
    def test_exact_source_replay(self):
        result=assess_archive_compatibility(self.freeze())
        self.assertEqual(result["reason"],"EXACT_SOURCE_REPLAY_OK")
        self.assertTrue(result["historic_replay_verified"])
        self.assertFalse(result["migration_allowed"])
    def test_model_drift_is_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            for relative in MODEL_FILES:
                p=Path(directory)/relative
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(Path(relative).read_bytes())
            record=self.freeze(root=directory)
            p=Path(directory)/MODEL_FILES[0]
            p.write_bytes(p.read_bytes()+b"\n# upgraded\n")
            result=assess_archive_compatibility(record,root=directory)
            self.assertEqual(result["reason"],"MODEL_SOURCE_DRIFT")
            self.assertEqual(result["changed_files"],[MODEL_FILES[0]])
            self.assertFalse(result["historic_replay_verified"])
    def test_tampered_archive_rejected(self):
        record=self.freeze()
        record["model"]["home_xg"]=99
        self.assertEqual(assess_archive_compatibility(record)["reason"],
                         "INVALID_OR_UNVERIFIABLE_ARCHIVE")
    def test_missing_archive_rejected(self):
        self.assertEqual(assess_archive_compatibility({})["reason"],
                         "INVALID_OR_UNVERIFIABLE_ARCHIVE")
if __name__=="__main__":unittest.main()
