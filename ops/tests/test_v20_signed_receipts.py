import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from ops.v20_signed_receipts import audit_fixture,sha,DOMAIN,trust_policy
from ops.tests.test_v6_forward_archive_audit import archive
from ops.tests.test_v6_forward_comparison import NOW,KO

def enc(x):return json.dumps(x,sort_keys=True,separators=(",",":")).encode()

@unittest.skipUnless(shutil.which("openssl"),"OpenSSL missing")
class SignedReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root=Path(cls.tmp.name);cls.keys=[]
        for i in range(3):
            p=cls.root/f"k{i}.pem"
            subprocess.run(["openssl","genpkey","-algorithm","ED25519","-out",str(p)],check=True,capture_output=True,timeout=10)
            pub=subprocess.run(["openssl","pkey","-in",str(p),"-pubout","-outform","DER"],check=True,capture_output=True,timeout=10).stdout
            cls.keys.append({"key_id":f"test-{i}","organization":f"synthetic-org-{i}","origin":f"test-origin-{i}",
                "role":"witness" if i==0 else "result","public_key_hex":pub[-32:].hex(),
                "valid_from_utc":(NOW-timedelta(days=1)).isoformat(),"valid_until_utc":(KO+timedelta(days=1)).isoformat()})
    def sign(self,payload,i):
        f=self.root/"message";f.write_bytes(DOMAIN+payload)
        return subprocess.run(["openssl","pkeyutl","-sign","-inkey",str(self.root/f"k{i}.pem"),"-rawin","-in",str(f)],
                              check=True,capture_output=True,timeout=10).stdout.hex()
    def inputs(self,conflict=False,shared_org=False,late=False):
        raw=archive();keys=[dict(k) for k in self.keys]
        if shared_org:keys[2]["organization"]=keys[1]["organization"]
        policy=enc({"schema":"v20-independent-trust-policy-v1","keys":keys})
        wt=KO if late else NOW+timedelta(seconds=1)
        w=enc({"schema":"v20-archive-witness-v1","key_id":"test-0","origin":"test-origin-0","signed_utc":wt.isoformat(),"archive_sha256":sha(raw)})
        results=[]
        for i in (1,2):
            src=enc({"synthetic_provider":i,"score":[2,1]})
            q=enc({"schema":"v20-result-receipt-v1","key_id":f"test-{i}","origin":f"test-origin-{i}",
                "signed_utc":(KO+timedelta(hours=3)).isoformat(),"archive_sha256":sha(raw),"fixture_id":"1",
                "home_native_id":"2","away_native_id":"3","kickoff_utc":KO.isoformat(),
                "observed_utc":(KO+timedelta(hours=2)).isoformat(),"raw_sha256":sha(src),
                "scope":"FULL_MATCH_REGULATION","status":"FINISHED","home_goals":3 if conflict and i==2 else 2,"away_goals":1})
            results.append((q,self.sign(q,i),src))
        return [raw,policy,sha(policy),(w,self.sign(w,0)),results]
    def run_case(self,a):
        return audit_fixture(*a,fixture_id="1",as_of_utc=(KO+timedelta(hours=4)).isoformat())
    def test_real_crypto_synthetic_only(self):
        r=self.run_case(self.inputs())
        self.assertTrue(r["signature_checks_passed"]);self.assertEqual(r["claimed_final_score"],[2,1])
        self.assertEqual(r["verified_forward_sample_credit"],0)
        self.assertFalse(r["actual_source_independence_verified"])
    def test_tampered_signature_and_policy(self):
        a=self.inputs();a[3]=(a[3][0], "00"*64)
        with self.assertRaisesRegex(ValueError,"SIGNATURE_INVALID"):self.run_case(a)
        a=self.inputs();a[2]="0"*64
        with self.assertRaisesRegex(ValueError,"TRUST_POLICY_DIGEST"):self.run_case(a)
    def test_source_conflict_and_raw_tamper(self):
        with self.assertRaisesRegex(ValueError,"RESULT_CONFLICT"):self.run_case(self.inputs(conflict=True))
        with self.assertRaisesRegex(ValueError,"ORIGIN_CONFLICT"):self.run_case(self.inputs(shared_org=True))
        a=self.inputs();q,s,_=a[4][0];a[4][0]=(q,s,b"changed")
        with self.assertRaisesRegex(ValueError,"RAW_HASH"):self.run_case(a)
    def test_late_witness(self):
        with self.assertRaisesRegex(ValueError,"CLOCK|LATE"):self.run_case(self.inputs(late=True))
