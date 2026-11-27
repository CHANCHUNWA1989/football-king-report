import json,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import timedelta
from ops.v22_forward_ledger import open_ledger,register,settle,report,sha
from ops.tests.test_v6_forward_archive_audit import archive
from ops.tests.test_v6_forward_comparison import NOW,KO,result
from ops.tests.test_v21_raw_results import inputs,enc

class ForwardLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"ledger.db";self.db=open_ledger(self.path)
        self.addCleanup(lambda:self.db.close())
        self.raw=archive();self.created=(NOW+timedelta(seconds=1)).isoformat()
        self.obs=(KO+timedelta(hours=3)).isoformat()
    def register(self):
        return register(self.db,self.raw,sha(self.raw),self.created,as_of=self.obs)
    def test_reopen_and_duplicate(self):
        self.assertEqual(self.register()["inserted"],1)
        self.db.close();self.db=open_ledger(self.path)
        self.assertEqual(self.register()["duplicates"],1)
        r=report(self.db)
        self.assertEqual((r["archive_count"],r["unique_fixture_count"],r["pending_count"]),(1,1,1))
        self.assertEqual(r["verified_forward_sample_credit"],0)
    def test_single_then_dual_unique_count(self):
        self.register();ol,fd,m=inputs()
        self.assertFalse(settle(self.db,"1",enc(ol),self.obs,as_of=self.obs)["duplicate"])
        self.assertTrue(settle(self.db,"1",enc(ol),self.obs,as_of=self.obs)["duplicate"])
        raw=enc(m)
        settle(self.db,"1",enc(ol),self.obs,fd_raw=enc(fd),fd_observed_utc=self.obs,
               mapping_raw=raw,mapping_sha256=sha(raw),as_of=self.obs)
        r=report(self.db)
        self.assertEqual((r["settled_research_count"],r["dual_raw_research_count"],r["pending_count"]),(1,1,0))
        self.assertEqual(r["paired_research_metrics"]["baseline"]["n"],1)
        self.assertEqual(r["verified_forward_sample_credit"],0)
    def test_conflict_and_no_overwrite(self):
        self.register();ol=result()
        settle(self.db,"1",enc(ol),self.obs,as_of=self.obs)
        ol[0]["matchResults"][0]["pointsTeam1"]=3
        with self.assertRaisesRegex(ValueError,"SETTLEMENT_SCORE_CONFLICT"):
            settle(self.db,"1",enc(ol),self.obs,as_of=self.obs)
        self.assertEqual(report(self.db)["settled_research_count"],1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM fixtures")
    def test_reject_late_future_and_tampered_archive(self):
        with self.assertRaises(ValueError):
            register(self.db,self.raw,"0"*64,self.created,as_of=self.obs)
        with self.assertRaisesRegex(ValueError,"FUTURE_ARCHIVE"):
            register(self.db,self.raw,sha(self.raw),self.created,as_of=NOW.isoformat())
        self.register()
        with self.assertRaisesRegex(ValueError,"FUTURE_RESULT"):
            settle(self.db,"1",enc(result()),self.obs,as_of=NOW.isoformat())
        self.assertEqual(report(self.db)["pending_count"],1)
