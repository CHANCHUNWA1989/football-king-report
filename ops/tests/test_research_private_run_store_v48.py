import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from ops.research_private_run_store_v48 import save,load,encode_run,verify_run
from ops.research_integrated_fusion_v45 import prepare
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.tests.test_research_private_propline_v43 import fixture as market_fixture,NOW
from ops.research_prospective_fusion_v38 import canonical

def inputs():
    raw,p=fixture()
    batch={"raw":encode({"events":[market_fixture()]}),"league":"epl","captured_utc":NOW.isoformat()}
    packets,_=prepare(raw,[("p",encode(p))],[],None,[batch],as_of=NOW.isoformat())
    return batch,packets

class PrivateRunStoreTests(unittest.TestCase):
    def dirs(self,t):
        repo=Path(t)/"repo";repo.mkdir()
        store=Path(t)/"store";store.mkdir(mode=0o700)
        return repo,store
    def test_save_replay_and_no_overwrite(self):
        b,p=inputs()
        with TemporaryDirectory() as t:
            repo,store=self.dirs(t)
            r=save(store,repo,b,p)
            self.assertEqual(load(store,repo,r["run_sha256"]),r)
            self.assertEqual(r["local_receipts"],1)
            self.assertFalse(r["external_witness_verified"])
            self.assertFalse(r["historical_reference_bytes_rechecked"])
            self.assertEqual(len(list(store.iterdir())),1)
            self.assertEqual(next(store.iterdir()).stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):save(store,repo,b,p)
            self.assertEqual(len(list(store.iterdir())),1)
    def test_tampered_run_rejected(self):
        b,p=inputs()
        with TemporaryDirectory() as t:
            repo,store=self.dirs(t)
            r=save(store,repo,b,p)
            f=store/(r["run_sha256"]+".json")
            f.write_bytes(f.read_bytes()+b" ")
            with self.assertRaises(ValueError):load(store,repo,r["run_sha256"])
    def test_changed_route_rejected(self):
        b,p=inputs()
        d=json.loads(encode_run(b,p))
        d["packets"][0]["market_route"]["component"]["market"]["p"]=[.8,.1,.1]
        with self.assertRaises(ValueError):verify_run(canonical(d))
    def test_changed_history_ref_rejected(self):
        b,p=inputs()
        d=json.loads(encode_run(b,p))
        d["packets"][0]["history_references"][0][0]["decoded_sha256"]="0"*64
        with self.assertRaises(ValueError):verify_run(canonical(d))
    def test_repository_and_unsafe_permissions_rejected(self):
        b,p=inputs()
        with TemporaryDirectory() as t:
            repo,store=self.dirs(t)
            inside=repo/"private";inside.mkdir(mode=0o700)
            with self.assertRaises(ValueError):save(inside,repo,b,p)
            store.chmod(0o755)
            with self.assertRaises(ValueError):save(store,repo,b,p)
    def test_symlink_root_rejected(self):
        b,p=inputs()
        with TemporaryDirectory() as t:
            repo,store=self.dirs(t)
            link=Path(t)/"link";link.symlink_to(store,target_is_directory=True)
            with self.assertRaises(OSError):save(link,repo,b,p)
    def test_reflected_credential_rejected(self):
        b,p=inputs()
        with TemporaryDirectory() as t:
            repo,store=self.dirs(t)
            with self.assertRaises(ValueError):save(store,repo,b,p,credential="Arsenal")
            self.assertEqual(list(store.iterdir()),[])
