import json
import unittest
from datetime import timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from ops.v23_forward_cycle import cycle,backup,sha,URLS
from ops.v22_forward_ledger import open_ledger,register,report
from ops.tests.test_v6_forward_archive_audit import archive
from ops.tests.test_v6_forward_comparison import NOW,KO,result

class ForwardCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"ledger.sqlite"
        self.db=open_ledger(self.path);self.addCleanup(self.db.close)
        raw=archive();register(self.db,raw,sha(raw),(NOW+timedelta(seconds=1)).isoformat(),
            as_of=(NOW+timedelta(minutes=1)).isoformat())
        self.now=KO+timedelta(hours=3);self.calls=[]
    def capture(self,provider,year):
        self.calls.append((provider,year))
        raw=json.dumps(result()).encode()
        return raw,{"provider":provider,"season":year,"source":URLS[provider]+str(year),
            "captured_utc":self.now.isoformat(),"sha256":sha(raw),"bytes":len(raw),"source_authenticated":False}
    def test_future_fixture_no_request(self):
        out=cycle(self.db,capture_fn=self.capture,clock=lambda:NOW)
        self.assertEqual(out["due_at_start"],0)
        self.assertEqual(self.calls,[])
    def test_due_settlement_and_repeated_cycle(self):
        out=cycle(self.db,capture_fn=self.capture,clock=lambda:self.now)
        self.assertEqual(out["newly_settled"],1)
        self.assertEqual(len(self.calls),1)
        out=cycle(self.db,capture_fn=self.capture,clock=lambda:self.now)
        self.assertEqual(out["due_at_start"],0)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(out["ledger"]["settled_research_count"],1)
        self.assertEqual(out["verified_forward_sample_credit"],0)
    def test_failure_leaves_pending(self):
        def bad(provider,year):
            raw,meta=self.capture(provider,year);meta["sha256"]="0"*64
            return raw,meta
        out=cycle(self.db,capture_fn=bad,clock=lambda:self.now)
        self.assertEqual(out["reasons"]["SOURCE_UNAVAILABLE_OR_INVALID"],1)
        self.assertEqual(out["ledger"]["pending_count"],1)
        self.assertEqual(cycle(self.db,capture_fn=self.capture,clock=lambda:self.now)["newly_settled"],1)
    def test_backup_reopen_and_no_overwrite(self):
        cycle(self.db,capture_fn=self.capture,clock=lambda:self.now)
        dest=Path(self.tmp.name)/"backup.sqlite"
        out=backup(self.db,dest)
        self.assertEqual(out["sha256"],sha(dest.read_bytes()))
        copy=open_ledger(dest)
        try:self.assertEqual(report(copy),report(self.db))
        finally:copy.close()
        with self.assertRaises(FileExistsError):backup(self.db,dest)
