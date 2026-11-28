import unittest
import remote_anchor as a
import deployment_checkpoint as c

class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.old=c.canonical(dict(schema=c.SCHEMA,release="HOLD",production_recommendations="DISABLED",stopped=False,jobs=[],cycles=[dict(slot=0,status="SUCCEEDED",summary={"synthetic":True})]))
        self.new=c.canonical(dict(schema=c.SCHEMA,release="HOLD",production_recommendations="DISABLED",stopped=False,jobs=[],cycles=[dict(slot=i,status="SUCCEEDED",summary={"synthetic":True}) for i in (0,21600)]))
        self.m=dict(schema="fk-v34-remote-drill-v1",generation=2,classification="SYNTHETIC_ONLY",parent=a.GENESIS,release="HOLD",production_recommendations="DISABLED")
    def test_valid(self): self.assertEqual(a.validate(self.old,self.new,self.m,a.TIP,a.GENESIS)["generation"],2)
    def test_wrong_tip(self):
        with self.assertRaises(ValueError): a.validate(self.old,self.new,self.m,"a"*40,a.GENESIS)
    def test_wrong_parent(self):
        with self.assertRaises(ValueError): a.validate(self.old,self.new,self.m,a.TIP,"a"*40)
    def test_manifest_parent(self):
        with self.assertRaises(ValueError): a.validate(self.old,self.new,{**self.m,"parent":"b"*40},a.TIP,a.GENESIS)
    def test_generation_rollback(self):
        with self.assertRaises(ValueError): a.validate(self.old,self.new,{**self.m,"generation":1},a.TIP,a.GENESIS)
    def test_same_state(self):
        with self.assertRaises(ValueError): a.validate(self.old,self.old,self.m,a.TIP,a.GENESIS)
    def test_bad_classification(self):
        with self.assertRaises(ValueError): a.validate(self.old,self.new,{**self.m,"classification":"LIVE"},a.TIP,a.GENESIS)
    def test_bad_flags(self):
        with self.assertRaises(ValueError): a.validate(self.old,self.new,{**self.m,"release":"READY"},a.TIP,a.GENESIS)
    def test_extra_manifest(self):
        with self.assertRaises(ValueError): a.validate(self.old,self.new,{**self.m,"approved":True},a.TIP,a.GENESIS)
    def test_unprotected(self):
        self.assertFalse(a.protection({"protected":False},[])["deploymentAuthorized"])
    def test_protected_not_approval(self):
        x=a.protection({"protected":True},[{"type":"non_fast_forward"},{"type":"deletion"}])
        self.assertTrue(x["protectedReported"])
        self.assertFalse(x["deploymentAuthorized"])
    def test_unknown_protection(self):
        self.assertIsNone(a.protection({},None)["protectedReported"])
    def test_malformed_protection(self):
        self.assertIsNone(a.protection({"protected":"true"},[])["protectedReported"])
if __name__=="__main__": unittest.main(verbosity=2)
