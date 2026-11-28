import json
import unittest
from datetime import timedelta
from ops.research_private_acquisition_v47 import acquire,PATHS
from ops.tests.test_research_private_propline_v43 import fixture,NOW

def body(x):return json.dumps(x).encode()
def now():return NOW.isoformat()
def active():return body([{"key":"soccer_epl","active":True}])
class PrivateAcquisitionTests(unittest.TestCase):
    def test_valid_bounded_acquisition(self):
        paths=[]
        def fetch(path,key):
            paths.append(path)
            return (active(),900) if path=="/sports" else (body([fixture()]),899)
        b,r=acquire("epl",key="synthetic",fetcher=fetch,now=now)
        self.assertEqual(paths,["/sports",PATHS["epl"]])
        self.assertEqual(r["market_components"],1)
        self.assertEqual(r["requests_attempted"],2)
        self.assertNotIn("Arsenal",json.dumps(r))
        self.assertFalse(r["publication_allowed"])
        self.assertEqual(len(b),1)
    def test_quota_missing_or_reserve(self):
        for q in (None,True,75,-1):
            paths=[]
            def fetch(path,key):
                paths.append(path);return active(),q
            b,r=acquire("epl",key="synthetic",fetcher=fetch,now=now)
            self.assertEqual(paths,["/sports"])
            self.assertEqual(b,[])
    def test_missing_second_quota(self):
        def fetch(path,key):
            return (active(),900) if path=="/sports" else (body([fixture()]),None)
        b,r=acquire("epl",key="synthetic",fetcher=fetch,now=now)
        self.assertEqual(b,[])
        self.assertEqual(r["requests_attempted"],2)
        self.assertIsNone(r["remaining"])
    def test_no_key_or_before_registration(self):
        def bomb(*args):self.fail("unexpected request")
        for key,t in (("",now),("synthetic",lambda:"2026-11-27T23:59:00Z")):
            b,r=acquire("epl",key=key,fetcher=bomb,now=t)
            self.assertEqual(r["requests_attempted"],0)
            self.assertEqual(b,[])
    def test_wrong_catalogue(self):
        def fetch(path,key):return body([{"key":"soccer_epl","active":False}]),900
        b,r=acquire("epl",key="synthetic",fetcher=fetch,now=now)
        self.assertEqual(r["requests_attempted"],1)
        self.assertEqual(b,[])
    def test_duplicate_json_rejected(self):
        def fetch(path,key):
            return (active(),900) if path=="/sports" else (b'[{"id":"a","id":"b"}]',899)
        b,r=acquire("epl",key="synthetic",fetcher=fetch,now=now)
        self.assertEqual(b,[])
        self.assertEqual(r["reason"],"PROVIDER_OR_INPUT_REJECTED")
    def test_clock_delay_rejected(self):
        def fetch(path,key):
            return (active(),900) if path=="/sports" else (body([fixture()]),899)
        times=iter([now(),(NOW+timedelta(minutes=3)).isoformat()])
        b,r=acquire("epl",key="synthetic",fetcher=fetch,now=lambda:next(times))
        self.assertEqual(b,[])
        self.assertEqual(r["reason"],"ACQUISITION_CLOCK_REJECTED")
