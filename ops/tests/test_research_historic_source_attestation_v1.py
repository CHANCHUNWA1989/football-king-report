import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from ops.research_market_provenance_v1 import Quote
from ops.research_model_source_binding_v1 import MODEL_FILES,freeze_versioned_pricing_evidence
from ops.research_historic_source_attestation_v1 import attest_historical_source

class HistoricSourceAttestationTests(unittest.TestCase):
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
    def freeze(self):
        return freeze_versioned_pricing_evidence(event_id="fixture",
            home_xg=1.5,away_xg=1.1,quotes=self.quotes,now=self.now,
            handicap_line=-0.25,totals_line=2.5)
    def test_matching_source_bytes_not_executed(self):
        record=self.freeze()
        result=attest_historical_source(record,historic_root=".")
        self.assertEqual(result["reason"],"HISTORIC_SOURCE_BYTES_MATCH")
        self.assertTrue(result["historic_source_bytes_matched"])
        self.assertFalse(result["execution_permitted"])
        self.assertFalse(result["historic_replay_verified"])
    def test_missing_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result=attest_historical_source(self.freeze(),historic_root=directory)
            self.assertEqual(result["reason"],"HISTORIC_SOURCE_UNAVAILABLE")
    def test_mismatched_source_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            for relative in MODEL_FILES:
                p=Path(directory)/relative
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(Path(relative).read_bytes())
            p=Path(directory)/MODEL_FILES[0]
            p.write_bytes(p.read_bytes()+b"\n#changed\n")
            result=attest_historical_source(self.freeze(),historic_root=directory)
            self.assertEqual(result["reason"],"HISTORIC_SOURCE_MISMATCH")
    def test_tampered_record_fails(self):
        record=self.freeze()
        record["model"]["home_xg"]=42
        self.assertEqual(attest_historical_source(record,historic_root=".")["reason"],
                         "INVALID_ARCHIVE")
if __name__=="__main__":unittest.main()
