import gzip
import json
import unittest
from datetime import timedelta,datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from ops.tests.test_research_prospective_market_v41 import fixture,NOW
from ops.research_market_archive_readiness import scan

class MarketArchiveReadinessTests(unittest.TestCase):
    def test_archive_clock_not_filename_and_hold_reason(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);base=root/"market";base.mkdir()
            d=fixture();raw=json.dumps(d).encode();(base/"latest.json").write_bytes(raw)
            folder=base/"history"/NOW.strftime("%Y/%m/%d");folder.mkdir(parents=True)
            for name in ("1-1","2-1"):
                (folder/(name+".json.gz")).write_bytes(gzip.compress(raw))
            hold=dict(d,status="HOLD",reason="QUOTA_FLOOR",events=[],event_count=0,
                      as_of_utc=NOW.isoformat())
            (folder/"3-1.json.gz").write_bytes(gzip.compress(json.dumps(hold).encode()))
            (folder/"4-1.json.gz").write_bytes(b"bad")
            r=scan(root,as_of=NOW.isoformat())
            self.assertEqual(r["archive_counts"]["valid_files"],3)
            self.assertEqual(r["archive_counts"]["invalid_files"],1)
            self.assertEqual(r["archive_counts"]["newer_than_latest"],1)
            self.assertEqual(r["unique_decoded_archives"],2)
            self.assertEqual(r["archive_hold_reasons"],{"QUOTA_FLOOR":1})
            self.assertEqual((base/"latest.json").read_bytes(),raw)
            self.assertFalse(r["source_authenticity_verified"])
    def test_actual_archive_read_only(self):
        root=Path(__file__).resolve().parents[2];p=root/"market/latest.json";raw=p.read_bytes()
        r=scan(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(p.read_bytes(),raw)
        self.assertEqual(r["provider_calls_made"],0)
        self.assertEqual(r["authenticated_samples"],0)
        print("V48_MARKET_ARCHIVE_READINESS "+json.dumps(r,sort_keys=True,allow_nan=False))
