import concurrent.futures
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vnext_quota_ledger_offline import initialize, reserve


class QuotaLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"research.db"
        initialize(self.path)

    def attempt(self, request_id, **overrides):
        args=dict(request_id=request_id,consumer="simulator",now=100000,
                  observed=100000,daily_remaining=100,minute_remaining=10)
        args.update(overrides)
        out=reserve(self.path,**args)
        self.assertFalse(out["real_request_authorized"])
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertEqual(out["status"],"HOLD")
        return out

    def test_parallel_consumers_share_nine_attempt_limit(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            rows=list(pool.map(lambda n:self.attempt("req"+str(n),consumer="consumer"+str(n%3)),range(32)))
        self.assertEqual(sum(x["simulated_reservation"] for x in rows),9)
        self.assertEqual(sum(x["reason"]=="QUOTA_RESERVE" for x in rows),23)

    def test_same_id_concurrency(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            rows=list(pool.map(lambda n:self.attempt("same",consumer="consumer"+str(n)),range(16)))
        self.assertEqual(sum(x["simulated_reservation"] for x in rows),1)
        self.assertEqual(sum(x["reason"]=="REPLAY" for x in rows),15)

    def test_clock_rollback_and_persisted_reservation(self):
        self.assertTrue(self.attempt("a")["simulated_reservation"])
        self.assertEqual(self.attempt("b",now=99999,observed=99999)["reason"],"CLOCK_ROLLBACK")
        self.assertEqual(self.attempt("a",now=100061,observed=100061)["reason"],"REPLAY")

    def test_declared_quota_and_minute_boundary(self):
        self.assertTrue(self.attempt("a",daily_remaining=2)["simulated_reservation"])
        self.assertEqual(self.attempt("b",daily_remaining=2)["reason"],"QUOTA_RESERVE")
        for i in range(8):
            self.assertTrue(self.attempt("m"+str(i))["simulated_reservation"])
        self.assertEqual(self.attempt("edge",now=100060,observed=100060)["reason"],"QUOTA_RESERVE")
        self.assertTrue(self.attempt("later",now=100061,observed=100061)["simulated_reservation"])

    def test_rolling_daily_cap_and_boundary(self):
        for i in range(99):
            t=100000+i*61
            self.assertTrue(self.attempt("day"+str(i),now=t,observed=t)["simulated_reservation"])
        self.assertEqual(self.attempt("over",now=186400,observed=186400)["reason"],"QUOTA_RESERVE")
        self.assertTrue(self.attempt("next",now=186401,observed=186401)["simulated_reservation"])

    def test_bad_evidence(self):
        for kw in (dict(observed=999),dict(observed=100001),dict(daily_remaining=True),
                   dict(minute_remaining=1),dict(now=False),dict(daily_remaining=101)):
            self.assertEqual(self.attempt("bad",**kw)["reason"],"BAD_EVIDENCE")
        self.assertEqual(self.attempt("bad/id")["reason"],"BAD_ID")

    def test_missing_or_corrupt_ledger_is_not_recreated(self):
        self.path.unlink()
        self.assertEqual(self.attempt("a")["reason"],"LEDGER_UNAVAILABLE")
        self.assertFalse(self.path.exists())
        self.path.write_bytes(b"not a database")
        self.assertEqual(self.attempt("a")["reason"],"LEDGER_UNAVAILABLE")

    def test_invalid_clock_state(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM clock")
        self.assertEqual(self.attempt("a")["reason"],"INVALID_LEDGER")
