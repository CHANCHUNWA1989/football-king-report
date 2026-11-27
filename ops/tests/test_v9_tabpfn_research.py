import hashlib
import tempfile
import unittest
from pathlib import Path
from ops.v9_tabpfn_research import checkpoint,predict,calibrate,blend,FILENAMES

class FakeClassifier:
    classes_=[0,1,2]
    def predict_proba(self,x):
        return [[.5,.3,.2] for _ in x]

class FoundationTests(unittest.TestCase):
    def test_checkpoint_gate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/FILENAMES[0];p.write_bytes(b"synthetic-not-a-model")
            sha=hashlib.sha256(p.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,"LICENSE_REVIEW_REQUIRED"):checkpoint(p,sha,False)
            with self.assertRaisesRegex(ValueError,"CHECKPOINT_HASH_MISMATCH"):checkpoint(p,"0"*64,True)
            self.assertEqual(checkpoint(p,sha,True),p.resolve())
    def test_prediction_contract(self):
        m=FakeClassifier()
        self.assertEqual(len(predict(m,[{"x":[0.]*19}]*130)),130)
        m.classes_=[2,1,0]
        with self.assertRaisesRegex(ValueError,"FOUNDATION_CLASS_ORDER"):predict(m,[{"x":[0.]*19}])
    def test_calibration_only_and_zero_weight(self):
        rows=[{"season":"2024-25","y":i%3} for i in range(210)]
        a=[[.5,.3,.2]]*210;b=[[.34,.33,.33]]*210
        self.assertEqual(blend(a[0],b[0],1.,0.),a[0])
        t,w=calibrate(rows,a,b)
        self.assertIn(t,(.8,1.,1.2,1.5));self.assertIn(w,(0.,.25,.5,.75,1.))
        rows[-1]["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"FOUNDATION_CAL_SCOPE"):calibrate(rows,a,b)
