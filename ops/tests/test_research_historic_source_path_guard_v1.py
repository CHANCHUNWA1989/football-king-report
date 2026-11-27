import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_model_source_binding_v1 import MODEL_FILES,freeze_versioned_pricing_evidence
from ops.research_historic_source_attestation_v1 import attest_historical_source

class HistoricSourcePathGuardTests(unittest.TestCase):
    def setUp(self):
        now=datetime(2026,11,27,12,tzinfo=timezone.utc)
        quotes=[]
        for market,selection,line in (
            ("handicap","home",-0.25),("handicap","away",-0.25),
            ("totals","over",2.5),("totals","under",2.5)):
            for source,upstream in (("a","up-a"),("b","up-b")):
                quotes.append(Quote(source=source,upstream_provider=upstream,
                    bookmaker="book-a",event_id="fixture",market=market,
                    selection=selection,line=line,decimal_odds=1.91,
                    observed_at=now-timedelta(seconds=20),
                    kickoff_at=now+timedelta(hours=1)))
        self.record=freeze_versioned_pricing_evidence(
            event_id="fixture",home_xg=1.5,away_xg=1.1,quotes=quotes,
            now=now,handicap_line=-0.25,totals_line=2.5)
    def populate(self,root):
        for relative in MODEL_FILES:
            p=root/relative
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(Path(relative).read_bytes())
    def test_regular_source_matches(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"source"
            self.populate(root)
            result=attest_historical_source(self.record,historic_root=root)
            self.assertEqual(result["reason"],"HISTORIC_SOURCE_BYTES_MATCH")
    def test_symlinked_root_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"source"
            self.populate(root)
            link=Path(d)/"link"
            link.symlink_to(root,target_is_directory=True)
            result=attest_historical_source(self.record,historic_root=link)
            self.assertEqual(result["reason"],"HISTORIC_SOURCE_UNAVAILABLE")
    def test_symlinked_directory_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"source"
            self.populate(root)
            (root/"ops").rename(root/"actual_ops")
            (root/"ops").symlink_to(root/"actual_ops",target_is_directory=True)
            result=attest_historical_source(self.record,historic_root=root)
            self.assertEqual(result["reason"],"HISTORIC_SOURCE_MISMATCH")
    def test_symlinked_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"source"
            self.populate(root)
            p=root/MODEL_FILES[0]
            original=p.read_bytes()
            p.unlink()
            alternate=root/"alternate.py"
            alternate.write_bytes(original)
            p.symlink_to(alternate)
            result=attest_historical_source(self.record,historic_root=root)
            self.assertEqual(result["reason"],"HISTORIC_SOURCE_MISMATCH")
if __name__=="__main__":unittest.main()
