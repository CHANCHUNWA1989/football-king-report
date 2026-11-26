import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from ops.v27_stack_archive import seal,enc,sha
from ops.v32_stack_ledger import open_ledger,register,settle,report
from ops.tests.test_v27_stack_archive import inputs
from ops.tests.test_v6_forward_comparison import NOW,KO,result

class StackLedgerTests(unittest.TestCase):
    def test_restart_idempotence_and_first_forecast(self):
        a,b=inputs();raw=seal(enc(a),enc(b),NOW)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"ledger.db";db=open_ledger(p)
            try:
                first=register(db,raw,sha(raw),NOW)
                self.assertEqual(first["inserted"],1)
                self.assertEqual(first["production_recommendations"],"DISABLED")
                self.assertEqual(report(db)["pending_count"],1)
            finally:db.close()
            db=open_ledger(p)
            try:
                self.assertEqual(register(db,raw,sha(raw),NOW)["duplicates"],1)
                obs=KO+timedelta(hours=3)
                doc=enc(result())
                out=settle(db,"1",doc,obs,obs)
                self.assertFalse(out["duplicate"])
                self.assertEqual(out["verified_forward_sample_credit"],0)
                self.assertTrue(settle(db,"1",doc,obs,obs)["duplicate"])
                r=report(db)
                self.assertEqual(r["settled_count"],1)
                self.assertEqual(r["pending_count"],0)
                self.assertEqual(r["verified_forward_sample_credit"],0)
                self.assertEqual(r["status"],"HOLD")
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("DELETE FROM v32_fixtures")
            finally:db.close()
    def test_future_archive_and_result_rejected(self):
        a,b=inputs();raw=seal(enc(a),enc(b),NOW)
        with tempfile.TemporaryDirectory() as d:
            db=open_ledger(Path(d)/"ledger.db")
            try:
                with self.assertRaisesRegex(ValueError,"FUTURE_ARCHIVE"):
                    register(db,raw,sha(raw),NOW-timedelta(seconds=1))
                register(db,raw,sha(raw),NOW)
                with self.assertRaisesRegex(ValueError,"FUTURE_RESULT"):
                    settle(db,"1",enc(result()),KO+timedelta(hours=3),KO)
                self.assertEqual(report(db)["settled_count"],0)
            finally:db.close()
