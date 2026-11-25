import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import json
from ops.v10_fusion import blend,fit,compare
from ops.v10_release import build,FILES
def row(i=0,y=0):
    return {"league":"en.1","season":"2024-25","date":"2024-09-17","home":str(i),"away":"B","y":y,"dc":[.5,.3,.2],"ml":[.6,.2,.2]}
class FusionTests(unittest.TestCase):
    def test_fallback(self):
        r=row();r["ml"]=None
        for w in (0,.5,1):self.assertEqual(blend(r,w),r["dc"])
    def test_endpoints(self):
        r=row()
        for a,b in zip(blend(r,1),r["ml"]):self.assertAlmostEqual(a,b)
    def test_leakage(self):
        a=[row(i,i%3) for i in range(210)];a[-1]["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"DEVELOPMENT"):fit(a,.5)
    def test_missing_dev(self):
        a=[dict(row(i,i%3),ml=None) for i in range(210)]
        with self.assertRaisesRegex(ValueError,"FEATURES"):fit(a,.5)
    def test_full_denominator(self):
        a=row();b=dict(row(1),ml=None)
        for r in (a,b):r["fusion"]=blend(r,.5);r["half"]=r["fusion"]
        z=compare([a,b]);self.assertEqual(z["n"],2);self.assertEqual(z["fallback_n"],1)
        self.assertEqual(z["all_same_fixture"]["fusion"]["n"],2)
    def test_missing_report(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):build(d)
    def test_unsafe_report(self):
        with TemporaryDirectory() as d:
            Path(d,FILES["history"]).write_text(json.dumps({"status":"READY","production_recommendations":"ENABLED"}))
            with self.assertRaisesRegex(ValueError,"UNSAFE"):build(d)
