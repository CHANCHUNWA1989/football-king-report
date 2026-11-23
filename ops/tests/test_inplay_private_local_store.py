"""Synthetic private local store negative tests. No actual provider captures."""
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from datetime import timedelta

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inplay_private_claim_replay import make_private_package
from inplay_private_local_store import save_private_package, verify_private_package, StoreError
from test_inplay_two_source_byte_packet import fixture, pair, NOW


class PrivateLocalStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"secure"
        self.root.mkdir(mode=0o700)
        self.raw=make_private_package(fixture(),pair(),now=NOW)
        self.digest=hashlib.sha256(self.raw).hexdigest()
        self.name="inplay-"+self.digest+".tar"

    def test_create_only_private_save_and_later_readback(self):
        report=save_private_package(self.root,self.raw,now=NOW)
        self.assertEqual(report["status"],"RESEARCH_ONLY")
        self.assertTrue(report["local_filesystem_byte_readback_verified"])
        self.assertTrue(report["created_new_private_file"])
        self.assertFalse(report["raw_source_publisher_authenticated"])
        self.assertFalse(report["externally_witnessed"])
        self.assertFalse(report["durable_storage_independently_verified"])
        self.assertFalse(report["eligible_for_model_input"])
        self.assertFalse(report["positive_ev_verified"])
        self.assertEqual(report["certified_forward_samples"],0)
        self.assertEqual(report["production_recommendations"],"DISABLED")
        self.assertEqual(report["package_sha256_unattested"],self.digest)
        path=self.root/self.name
        self.assertEqual(path.read_bytes(),self.raw)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
        self.assertEqual(list(self.root.iterdir()),[path])
        recovered=verify_private_package(self.root,self.digest,now=NOW+timedelta(days=10))
        self.assertEqual(recovered["status"],"RESEARCH_ONLY")
        self.assertTrue(recovered["local_filesystem_byte_readback_verified"])
        self.assertFalse(recovered["durable_storage_independently_verified"])
        self.assertNotIn("www.sofascore",str(recovered))

    def test_idempotent_same_bytes_cannot_replace(self):
        first=save_private_package(self.root,self.raw,now=NOW)
        second=save_private_package(self.root,self.raw,now=NOW)
        self.assertTrue(first["created_new_private_file"])
        self.assertFalse(second["created_new_private_file"])
        self.assertEqual(list(self.root.iterdir()),[self.root/self.name])

    def test_tamper_existing_bytes_is_rejected(self):
        save_private_package(self.root,self.raw,now=NOW)
        (self.root/self.name).write_bytes(b"forged")
        self.assertEqual(verify_private_package(self.root,self.digest,now=NOW)["status"],"HOLD")
        with self.assertRaises(StoreError):
            save_private_package(self.root,self.raw,now=NOW)

    def test_wrong_digest_and_invalid_pin_do_not_open_original_bytes(self):
        save_private_package(self.root,self.raw,now=NOW)
        for digest in ("0"*64,"../../../etc/passwd","z"*64,"",True):
            report=verify_private_package(self.root,digest,now=NOW)
            self.assertEqual(report["status"],"HOLD")
            self.assertNotIn("www.fotmob.com",str(report))

    def test_symlink_collision_never_replaced(self):
        target=Path(self.tmp.name)/"outside"
        target.write_bytes(b"secret")
        (self.root/self.name).symlink_to(target)
        with self.assertRaises(StoreError):
            save_private_package(self.root,self.raw,now=NOW)
        self.assertEqual(target.read_bytes(),b"secret")
        self.assertEqual(verify_private_package(self.root,self.digest,now=NOW)["status"],"HOLD")

    def test_hardlink_archive_rejected(self):
        save_private_package(self.root,self.raw,now=NOW)
        os.link(self.root/self.name,self.root/"another")
        self.assertEqual(verify_private_package(self.root,self.digest,now=NOW)["status"],"HOLD")
        with self.assertRaises(StoreError):
            save_private_package(self.root,self.raw,now=NOW)

    def test_publicly_readable_directory_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(StoreError):
            save_private_package(self.root,self.raw,now=NOW)
        self.assertEqual(verify_private_package(self.root,self.digest,now=NOW)["status"],"HOLD")
        self.assertEqual(list(self.root.iterdir()),[])

    def test_directory_inside_git_repository_rejected(self):
        (Path(self.tmp.name)/".git").mkdir()
        with self.assertRaises(StoreError):
            save_private_package(self.root,self.raw,now=NOW)
        self.assertEqual(verify_private_package(self.root,self.digest,now=NOW)["status"],"HOLD")

    def test_symlink_directory_chain_rejected(self):
        linked=Path(self.tmp.name)/"linked"
        linked.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(StoreError):
            save_private_package(linked,self.raw,now=NOW)
        self.assertEqual(verify_private_package(linked,self.digest,now=NOW)["status"],"HOLD")

    def test_invalid_private_bytes_rejected_without_files(self):
        for raw in (b"secret",b"",None,self.raw+b"CORRUPTION"):
            with self.assertRaises(StoreError):
                save_private_package(self.root,raw,now=NOW)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_missing_private_directory_never_auto_created(self):
        missing=self.root/"not-yet-created"
        with self.assertRaises(StoreError):
            save_private_package(missing,self.raw,now=NOW)
        self.assertFalse(missing.exists())

    def test_no_sensitive_paths_or_source_urls_in_errors(self):
        secret="PRIVATE_PATH_SECRET"
        wrong=Path(self.tmp.name)/secret
        with self.assertRaises(StoreError) as failure:
            save_private_package(wrong,self.raw,now=NOW)
        self.assertNotIn(secret,str(failure.exception))
        self.assertNotIn("www.sofascore.com",str(failure.exception))


if __name__=="__main__":
    unittest.main()
