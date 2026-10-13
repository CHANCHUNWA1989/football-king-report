import hashlib
import tempfile
import unittest
from pathlib import Path
from shadow_raw_source_collector import collect

class CollectorTests(unittest.TestCase):
    def test_raw_bytes_hash_and_hold(self):
        payloads={"api.openligadb.de":b"[]","raw.githubusercontent.com":b'{"matches":[]}'}
        with tempfile.TemporaryDirectory() as folder:
            manifest=collect(2026,folder,getter=lambda url:next(v for k,v in payloads.items() if k in url))
            self.assertEqual(manifest["status"],"HOLD")
            self.assertFalse(manifest["independently_verified"])
            self.assertEqual(len(manifest["sources"]),2)
            for item in manifest["sources"]:
                body=next(v for k,v in payloads.items() if k in item["source_url"])
                self.assertEqual(item["raw_sha256"],hashlib.sha256(body).hexdigest())
                self.assertEqual((Path(folder)/item["raw_file"]).read_bytes(),body)
    def test_malformed_response_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=collect(2026,folder,getter=lambda url:b'not-json')
            self.assertEqual([s["status"] for s in manifest["sources"]],["ERROR","ERROR"])
            self.assertEqual(manifest["status"],"HOLD")
if __name__=="__main__":unittest.main()
