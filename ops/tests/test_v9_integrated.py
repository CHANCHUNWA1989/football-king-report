import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import json
from ops.v9_ucl_adaptive import adaptive,weight
from ops.v9_integrated_report import build,FILES
def row(d,h,y=0):
    return {"date":d,"home":h,"away":"B","y":y,"baseline":[.7,.2,.1],"elo":[.4,.3,.3],"hybrid":[.55,.25,.2]}
class AdaptiveTests(unittest.TestCase):
    def test_weight(self):
        self.assertEqual(weight([]),.5)
        self.assertGreater(weight([(.3,1.)]*96),.5)
        self.assertLess(weight([(1.,.3)]*96),.5)
    def test_same_day(self):
        a=[row("2024-09-17","A"),row("2024-09-17","C")]
        b=[dict(a[0],y=2),a[1]]
        self.assertEqual(adaptive(a)[1]["adaptive"],adaptive(b)[1]["adaptive"])
        self.assertEqual(adaptive(a)[1]["prior_n"],0)
    def test_duplicate(self):
        r=row("2024-09-17","A")
        with self.assertRaisesRegex(ValueError,"INVALID_CASE"):adaptive([r,r])
    def test_order(self):
        a=[row("2024-09-17","A"),row("2024-09-18","C")]
        self.assertEqual(adaptive(a),adaptive(list(reversed(a))))
    def test_missing_artifact(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):build(d)
    def test_unsafe_artifact(self):
        with TemporaryDirectory() as d:
            Path(d,FILES["domestic"]).write_text(json.dumps({"status":"READY","production_recommendations":"ENABLED"}))
            with self.assertRaisesRegex(ValueError,"UNSAFE"):build(d)
