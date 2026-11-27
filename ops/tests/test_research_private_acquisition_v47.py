import json
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from ops.research_private_acquisition_v47 import acquire,PATHS,pilot,preflight_history
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

class PrivateHistoryPreflightTests(unittest.TestCase):
    def inputs(self):
        from ops.tests.test_research_supplemental_provenance_v46 import inputs
        return inputs()
    def test_exact_history_before_spend(self):
        raw,p=self.inputs()
        self.assertEqual(preflight_history(raw,p,[],as_of=now()),2)
    def test_empty_history_rejected(self):
        raw,p=self.inputs()
        with self.assertRaises(ValueError):preflight_history(raw,[],[],as_of=now())
    def test_duplicate_archive_label_rejected(self):
        raw,p=self.inputs()
        with self.assertRaises(ValueError):preflight_history(raw,p+[p[0]],[],as_of=now())
    def test_reference_rejection_stops_pilot(self):
        raw,p=self.inputs()
        with TemporaryDirectory() as d:
            root=Path(d);(root/"evidence").mkdir()
            (root/"evidence/settled.json").write_bytes(raw)
            with patch("ops.research_private_acquisition_v47.archive_snapshots",return_value=p), \
                 patch("ops.research_private_acquisition_v47.secondary_snapshots",return_value=[]), \
                 patch("ops.research_private_acquisition_v47.verify_ref",side_effect=ValueError("bad ref")):
                def bomb(*args):self.fail("provider call after failed preflight")
                r=pilot(root,"epl",key="synthetic",fetcher=bomb,now=now)
            self.assertEqual(r["acquisition"]["requests_attempted"],0)
            self.assertEqual(r["acquisition"]["reason"],"HISTORY_PREFLIGHT_REJECTED")
            self.assertFalse(r["private_run_saved"])
    def test_valid_pilot_still_acquires(self):
        raw,p=self.inputs()
        with TemporaryDirectory() as d:
            root=Path(d);(root/"evidence").mkdir()
            (root/"evidence/settled.json").write_bytes(raw)
            paths=[]
            def fetch(path,key):
                paths.append(path)
                return (active(),900) if path=="/sports" else (body([fixture()]),899)
            with patch("ops.research_private_acquisition_v47.archive_snapshots",return_value=p), \
                 patch("ops.research_private_acquisition_v47.secondary_snapshots",return_value=[]):
                r=pilot(root,"epl",key="synthetic",fetcher=fetch,now=now)
            self.assertEqual(paths,["/sports",PATHS["epl"]])
            self.assertEqual(r["history_candidates"],2)
            self.assertEqual(r["local_receipts"],1)
            self.assertFalse(r["private_run_saved"])
