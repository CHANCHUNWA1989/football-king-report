import unittest,sqlite3
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import timedelta
from ops.v31_context_residual import features,adjust,select,GRID
from ops.v32_stack_ledger import open_ledger,register,settle,report
from ops.v27_stack_archive import seal,enc,sha
from ops.tests.test_v27_stack_archive import inputs
from ops.tests.test_v6_forward_comparison import NOW,KO,result

class ContextTests(unittest.TestCase):
    def test_same_day_score_invariance(self):
        from datetime import date
        a=date(2025,1,1)
        rows=[(a+timedelta(days=i),"A","B",1,0) for i in range(7)]
        key=(rows[-1][0].isoformat(),"A","B")
        original=features(rows)[key]
        self.assertIsNotNone(original)
        rows[-1]=(*rows[-1][:3],0,5)
        self.assertEqual(features(rows)[key],original)
    def test_mass_and_missing_context(self):
        r={"stack":[.5,.3,.2],"context":(.1,.2,.3,.4)}
        for p in GRID:self.assertAlmostEqual(sum(adjust(r,p)),1.)
        self.assertEqual(adjust({**r,"context":None},GRID[-1]),r["stack"])
    def test_calibration_no_future(self):
        rows=[{"season":"2024-25","date":"2025-01-01","y":i%3,"stack":[1/3]*3,"context":None} for i in range(120)]
        self.assertEqual(select(rows),(0.,0.,0.,0.))
        rows[-1]["date"]="2025-07-01"
        with self.assertRaisesRegex(ValueError,"CAL_SCOPE"):select(rows)

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"stack.sqlite";self.db=open_ledger(self.path)
        self.addCleanup(lambda:self.db.close());a,b=inputs()
        self.raw=seal(enc(a),enc(b),NOW);self.obs=KO+timedelta(hours=3)
    def test_reopen_and_same_fixture_count(self):
        self.assertEqual(register(self.db,self.raw,sha(self.raw),NOW)["inserted"],1)
        self.db.close();self.db=open_ledger(self.path)
        self.assertEqual(register(self.db,self.raw,sha(self.raw),NOW)["duplicates"],1)
        self.assertEqual(report(self.db)["pending_count"],1)
        self.assertFalse(settle(self.db,"1",enc(result()),self.obs,self.obs)["duplicate"])
        self.assertTrue(settle(self.db,"1",enc(result()),self.obs,self.obs)["duplicate"])
        x=report(self.db);self.assertEqual(x["settled_count"],1)
        self.assertEqual(x["metrics"]["v10_1"]["correct"],1);self.assertEqual(x["verified_forward_sample_credit"],0)
    def test_future_and_result_conflict(self):
        with self.assertRaisesRegex(ValueError,"FUTURE_ARCHIVE"):register(self.db,self.raw,sha(self.raw),NOW-timedelta(seconds=1))
        register(self.db,self.raw,sha(self.raw),NOW)
        with self.assertRaisesRegex(ValueError,"FUTURE_RESULT"):settle(self.db,"1",enc(result()),self.obs,NOW)
        settle(self.db,"1",enc(result()),self.obs,self.obs)
        x=result();x[0]["matchResults"][0]["pointsTeam1"]=3
        with self.assertRaisesRegex(ValueError,"RESULT_CONFLICT"):settle(self.db,"1",enc(x),self.obs,self.obs)
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute("DELETE FROM v32_results")
        self.assertEqual(report(self.db)["settled_count"],1)
