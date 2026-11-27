"""Synthetic tests; no network and no real event payloads."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from live_core_statsbomb_acquire import acquire, fetch_blob

def pin(raw):
    return hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()

class Response:
    def __init__(self,raw):self.raw=raw
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return self.raw[:n]

class AcquisitionTests(unittest.TestCase):
    def test_raw_blob_and_request_bound(self):
        raw=b"[]"
        with patch("live_core_statsbomb_acquire._open",return_value=Response(raw)) as op:
            self.assertEqual(fetch_blob(pin(raw),len(raw),'data/events/1.json'),raw)
            self.assertEqual(op.call_args.args[0].full_url,'https://raw.githubusercontent.com/hudl/open-data/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/data/events/1.json')
            self.assertEqual(op.call_args.kwargs["timeout"],20)

    def test_digest_or_length_mismatch(self):
        for raw in (b"{}",b"[] "):
            with patch("live_core_statsbomb_acquire._open",return_value=Response(raw)):
                with self.assertRaises(ValueError):fetch_blob(pin(b"[]"),2,"data/events/1.json")

    def test_complete_atomic_cohort_manifest(self):
        index=b"[]"; event=b"[1]"
        with tempfile.TemporaryDirectory() as d, patch("live_core_statsbomb_acquire.INDEX_BLOB",pin(index)),patch("live_core_statsbomb_acquire.INDEX_SIZE",len(index)),patch("live_core_statsbomb_acquire.EVENT_BLOBS",{"1":(pin(event),len(event))}),patch("live_core_statsbomb_acquire.fetch_blob",side_effect=[index,event]):
            target=Path(d)/"private"
            r=acquire(target,rights_confirmed=True)
            self.assertEqual(r["downloaded"],1)
            self.assertEqual((target/"1.json").read_bytes(),event)
            self.assertTrue((target/"manifest.json").is_file())
            self.assertFalse(r["source_authenticated"])

    def test_no_rights_or_failed_download_leaves_no_destination(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/"private"
            with patch("live_core_statsbomb_acquire.fetch_blob",side_effect=ValueError("FAIL")) as f:
                with self.assertRaises(ValueError):acquire(target,rights_confirmed=False)
                f.assert_not_called()
                with self.assertRaises(ValueError):acquire(target,rights_confirmed=True)
            self.assertFalse(target.exists())

    def test_existing_target_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/"private";target.mkdir()
            with patch("live_core_statsbomb_acquire.fetch_blob") as f:
                with self.assertRaises(ValueError):acquire(target,rights_confirmed=True)
                f.assert_not_called()
