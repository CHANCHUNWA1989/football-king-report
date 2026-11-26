import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from hashlib import sha1
from io import BytesIO
from ops.score_archive_tail_export_20261127 import export_cells,score_delta_bound
from ops.verify_historical_drift_replay_20261127 import fetch_blob,UPSTREAM_COMMIT
from ops.prospective_score_archive_v2_20261127 import derive

class TailExportTests(unittest.TestCase):
    def test_small_tail(self):
        p=5e-11
        r=export_cells({(0,0):.4,(2,1):.6-p,(31,0):p})
        self.assertAlmostEqual(r["discarded_fraction"],p)
        self.assertFalse(r["underlying_model_tail_verified"])
        g,m=derive(r["score_cells"])
        self.assertAlmostEqual(sum(g.values()),1)
        self.assertLessEqual(abs(m["one_x_two"][0]-(.6-p+p)),p+1e-15)
        self.assertIsNone(score_delta_bound(p)["exact_score_log_loss_bound"])
    def test_reject(self):
        for g in ({}, {(0,0):.99,(31,0):.01},{(0,0):.9},{(True,0):1},
                  {(0,0):float("nan")},{(0,0):True},{(31,0):1}):
            with self.subTest(g=g),self.assertRaises(ValueError): export_cells(g)
    def test_event_bounds(self):
        for p in (0,1e-12,5e-11,9e-11):
            for q in (.1,.5,.9):
                g={(0,0):q*(1-p),(2,1):(1-q)*(1-p),(0,31):p}
                r=export_cells(g)
                _,m=derive(r["score_cells"])
                for new,old in zip(m["one_x_two"],[(1-q)*(1-p),q*(1-p),p]):
                    self.assertLessEqual(abs(new-old),r["conditional_event_error_bound"]+1e-15)
    def test_order(self):
        self.assertEqual(export_cells({(2,1):.6,(0,0):.4}),export_cells({(0,0):.4,(2,1):.6}))

class PinnedSourceTests(unittest.TestCase):
    def test_verified_raw_and_retry(self):
        raw=b"fixture data"
        blob=sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
        with patch("ops.verify_historical_drift_replay_20261127.MANIFEST",{"EN":("en.1.json",1,(blob,))}),patch("ops.verify_historical_drift_replay_20261127.SEASONS",("2020-21",)),patch("ops.verify_historical_drift_replay_20261127.urlopen",side_effect=[HTTPError("https://example.invalid",503,"temporary",{},None),BytesIO(raw)]) as u,patch("ops.verify_historical_drift_replay_20261127.sleep"):
            self.assertEqual(fetch_blob(blob,"2020-21","en.1.json"),raw)
            self.assertEqual(u.call_count,2)
            self.assertIn(UPSTREAM_COMMIT,u.call_args.args[0].full_url)
    def test_hash_mismatch_and_unregistered(self):
        blob="081509058af75c0c012d64e980dc4fa53720d933"
        with patch("ops.verify_historical_drift_replay_20261127.urlopen",return_value=BytesIO(b"wrong")) as u:
            with self.assertRaises(ValueError): fetch_blob(blob,"2020-21","en.1.json")
            self.assertEqual(u.call_count,1)
            with self.assertRaises(ValueError): fetch_blob(blob,"../","en.1.json")
            self.assertEqual(u.call_count,1)

if __name__=="__main__": unittest.main()
