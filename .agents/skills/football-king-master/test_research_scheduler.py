"""V3.0 isolated SQLite scheduling tests; no provider requests."""
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import research_scheduler as s
import research_queue as q

class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state=Path(self.tmp.name)/"state"
        s.init(self.state)
    def test_slot_boundary(self):
        self.assertEqual(s.slot(21599),0)
        self.assertEqual(s.slot(21600),21600)
    def test_invalid_clock(self):
        for x in (-1,True,1.5):
            with self.assertRaises(ValueError): s.slot(x)
    def test_persist_claim(self):
        token=s.claim(self.state,21600)
        self.assertTrue(token)
        self.assertEqual(s.status(self.state)["cycles"][0]["status"],"RUNNING")
    def test_concurrent_claims(self):
        with ThreadPoolExecutor(max_workers=8) as ex:
            results=list(ex.map(lambda _:s.claim(self.state,21600),range(24)))
        self.assertEqual(sum(x is not None for x in results),1)
    def test_duplicate_completed_slot(self):
        token=s.claim(self.state,0)
        s.finish(self.state,0,token,"SUCCEEDED",{"stages":4})
        self.assertIsNone(s.claim(self.state,0))
        self.assertIsNotNone(s.claim(self.state,21600))
    def test_interrupted_blocks_later_slot(self):
        s.claim(self.state,0)
        self.assertIsNone(s.claim(self.state,21600))
    def test_backwards_clock_blocks(self):
        token=s.claim(self.state,21600)
        s.finish(self.state,21600,token,"SUCCEEDED",{})
        self.assertIsNone(s.claim(self.state,0))
    def test_failed_cycle_blocks_later(self):
        token=s.claim(self.state,0)
        s.finish(self.state,0,token,"BLOCKED",{})
        self.assertIsNone(s.claim(self.state,21600))
    def test_stop_persists(self):
        q.stop(self.state)
        self.assertTrue(s.status(self.state)["stopped"])
        self.assertIsNone(s.claim(self.state,0))
    def test_stop_while_running(self):
        token=s.claim(self.state,0)
        q.stop(self.state)
        s.finish(self.state,0,token,"SUCCEEDED",{})
        self.assertEqual(s.status(self.state)["cycles"][0]["status"],"BLOCKED")
    def test_wrong_token(self):
        token=s.claim(self.state,0)
        with self.assertRaises(ValueError): s.finish(self.state,0,"wrong","SUCCEEDED",{})
        s.finish(self.state,0,token,"SUCCEEDED",{})
    def test_retry_next_slot(self):
        token=s.claim(self.state,0)
        s.finish(self.state,0,token,"RETRY_WAIT",{})
        self.assertIsNone(s.claim(self.state,0))
        self.assertIsNotNone(s.claim(self.state,21600))
    def test_flags(self):
        self.assertEqual(s.status(self.state)["release"],"HOLD")
        self.assertEqual(s.status(self.state)["production_recommendations"],"DISABLED")
        self.assertFalse(s.status(self.state)["continuousOperationVerified"])
    def test_reinit(self):
        with self.assertRaises(FileExistsError): s.init(self.state)
    def test_status_has_no_token(self):
        s.claim(self.state,0)
        self.assertNotIn("token",s.status(self.state)["cycles"][0])
    def test_fake_evidence_rejected(self):
        with self.assertRaises(ValueError): s.check_result("evidence",{"certifiedN":1}, {})
    def test_fake_review_rejected(self):
        with self.assertRaises(ValueError): s.check_result("review",{"independentAgentReviews":4}, {})
    def test_fake_model_rejected(self):
        with self.assertRaises(ValueError): s.check_result("model",{"canChangeWeights":True}, {})
    def test_unknown_stage_rejected(self):
        with self.assertRaises(ValueError): s.check_result("other",{}, {})
if __name__=="__main__": unittest.main(verbosity=2)
