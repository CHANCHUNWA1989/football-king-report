import copy
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from ops.research_market_provenance_v1 import Quote
from ops.research_model_source_binding_v1 import (
    MODEL_FILES,model_source_manifest,freeze_versioned_pricing_evidence,
    verify_versioned_pricing_evidence)

class ModelSourceBindingTests(unittest.TestCase):
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
    def test_versioned_roundtrip(self):
        self.assertTrue(verify_versioned_pricing_evidence(self.freeze()))
    def test_manifest_tamper(self):
        record=self.freeze()
        record["model_source_manifest"]["sha256"]="0"*64
        self.assertFalse(verify_versioned_pricing_evidence(record))
    def test_missing_source_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                model_source_manifest(root=directory)
    def test_source_drift_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            for relative in MODEL_FILES:
                target=Path(directory)/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((Path(relative)).read_bytes())
            record=self.freeze(root=directory)
            self.assertTrue(verify_versioned_pricing_evidence(record,root=directory))
            (Path(directory)/MODEL_FILES[0]).write_text("changed model source")
            self.assertFalse(verify_versioned_pricing_evidence(record,root=directory))
if __name__=="__main__":unittest.main()
