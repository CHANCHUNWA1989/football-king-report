import copy
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_model_source_binding_v1 import MODEL_FILES,freeze_versioned_pricing_evidence
from ops.research_historic_source_snapshot_v1 import (
    prepare_historic_source_snapshot,verify_historic_source_snapshot)

class HistoricSourceSnapshotTests(unittest.TestCase):
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
    def test_snapshot_valid_and_no_execution(self):
        result=prepare_historic_source_snapshot(self.record,historic_root=".")
        self.assertEqual(result["reason"],"SOURCE_SNAPSHOT_CAPTURED_NOT_EXECUTED")
        self.assertTrue(verify_historic_source_snapshot(result["snapshot"],self.record))
        self.assertFalse(result["execution_permitted"])
    def test_snapshot_tamper_rejected(self):
        result=prepare_historic_source_snapshot(self.record,historic_root=".")
        snapshot=copy.deepcopy(result["snapshot"])
        key=MODEL_FILES[0]
        snapshot["files"][key]["bytes_hex"]="00"
        self.assertFalse(verify_historic_source_snapshot(snapshot,self.record))
    def test_missing_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            result=prepare_historic_source_snapshot(self.record,historic_root=d)
            self.assertEqual(result["reason"],"SOURCE_ATTESTATION_FAILED")
    def test_snapshot_survives_source_deletion(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for relative in MODEL_FILES:
                p=root/relative
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(Path(relative).read_bytes())
            result=prepare_historic_source_snapshot(self.record,historic_root=root)
            self.assertTrue(result["snapshot_verified"])
            for relative in MODEL_FILES:
                (root/relative).unlink()
            self.assertTrue(verify_historic_source_snapshot(result["snapshot"],self.record))
if __name__=="__main__":unittest.main()
