import concurrent.futures
import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vnext_quota_coordinator_contract import State, reserve_simulated


class MemoryCAS:
    """Synthetic linearizable store, no persistence or remote infrastructure."""
    def __init__(self):
        self.state=State("test",0,0,())
        self.lock=threading.Lock()
        self.calls=0

    def read(self):
        with self.lock:
            return self.state

    def cas(self,old,new):
        with self.lock:
            self.calls+=1
            if self.state != old:
                return False
            self.state=new
            return True


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.store=MemoryCAS()

    def attempt(self,request_id="r",**kw):
        args=dict(epoch="test",revision_floor=0,request_id=request_id,consumer="runner",
                  now=100000,observed=100000,daily_remaining=100,minute_remaining=10)
        args.update(kw)
        out=reserve_simulated(self.store,**args)
        self.assertFalse(out["real_request_authorized"])
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["production_recommendations"],"DISABLED")
        return out

    def test_parallel_clients_never_exceed_limit(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            rows=list(pool.map(lambda i:self.attempt("r"+str(i),consumer="runner"+str(i)),range(64)))
        accepted=sum(r["simulated_reservation"] for r in rows)
        self.assertTrue(1<=accepted<=9)
        self.assertEqual(accepted,len(self.store.state.attempts))
        self.assertTrue(all(r["reason"] in ("SIMULATED_ONLY","QUOTA_RESERVE","CAS_CONFLICT") for r in rows))

    def test_same_id_parallel(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            rows=list(pool.map(lambda i:self.attempt(consumer="runner"+str(i)),range(16)))
        self.assertEqual(sum(r["simulated_reservation"] for r in rows),1)
        self.assertEqual(len(self.store.state.attempts),1)

    def test_forced_cas_conflict_no_retry(self):
        self.store.cas=lambda old,new:False
        self.assertEqual(self.attempt()["reason"],"CAS_CONFLICT")
        self.assertEqual(self.store.state.revision,0)

    def test_commit_then_timeout_never_refund(self):
        original=self.store.cas
        def uncertain(old,new):
            original(old,new)
            raise TimeoutError()
        self.store.cas=uncertain
        self.assertEqual(self.attempt()["reason"],"STORE_UNAVAILABLE_OR_COMMIT_UNCERTAIN")
        self.assertEqual(self.store.calls,1)
        self.assertEqual(self.attempt()["reason"],"REPLAY")
        self.assertEqual(self.store.calls,1)

    def test_nonboolean_ack_is_uncertain(self):
        self.store.cas=lambda old,new:1
        self.assertEqual(self.attempt()["reason"],"COMMIT_UNCERTAIN")

    def test_missing_epoch_and_revision_rollback(self):
        self.assertEqual(self.attempt(epoch="other")["reason"],"INVALID_OR_ROLLED_BACK_STATE")
        self.assertEqual(self.attempt(revision_floor=1)["reason"],"INVALID_OR_ROLLED_BACK_STATE")
        self.assertEqual(self.store.calls,0)

    def test_invalid_state_and_clock(self):
        self.store.state=State("test",2,100000,(("r","x",99999),("r","x",100000)))
        self.assertEqual(self.attempt()["reason"],"INVALID_OR_ROLLED_BACK_STATE")
        self.store.state=State("test",0,100001,())
        self.assertEqual(self.attempt()["reason"],"CLOCK_ROLLBACK")

    def test_declared_quota_reserve(self):
        self.assertTrue(self.attempt(daily_remaining=2)["simulated_reservation"])
        self.assertEqual(self.attempt("b",daily_remaining=2)["reason"],"QUOTA_RESERVE")

    def test_bad_evidence(self):
        for kw in (dict(now=True),dict(observed=99699),dict(observed=100001),
                   dict(daily_remaining=1),dict(revision_floor=-1)):
            self.assertEqual(self.attempt(**kw)["reason"],"BAD_EVIDENCE")
        self.assertEqual(self.store.calls,0)
