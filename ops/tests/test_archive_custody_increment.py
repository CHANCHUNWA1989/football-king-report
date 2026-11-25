"""Adversarial lineage checks, synthetic fixture only."""
import hashlib
import unittest
from unittest.mock import patch
from copy import deepcopy
from ops.archive_custody_subject import canonical
from ops.archive_custody_increment import link, OLD_SOURCE, NEW_SOURCE, OLD_CANDIDATE, NEW_CANDIDATE, NEW_PATH, POINTER
from ops.history_blob_retention_preflight import RetentionHold


def report(subject):
    return {"subject":subject,"subject_sha256":hashlib.sha256(canonical(subject)).hexdigest()}


class CustodyIncrementTests(unittest.TestCase):
    def setUp(self):
        a=dict(source_main_sha=OLD_SOURCE, archive_candidate_sha=OLD_CANDIDATE,
               archive_base_sha="a"*40, history_records=[dict(path=str(i),digest=str(i)) for i in range(88)],
               mutable_pointer_records=[dict(path=str(i)) for i in range(12)]+[
                   dict(path=POINTER, archive_blob_sha1="a",archive_sha256="b",source_sha256="old")])
        b=deepcopy(a)
        b.update(source_main_sha=NEW_SOURCE,archive_candidate_sha=NEW_CANDIDATE)
        b["history_records"].append(dict(path=NEW_PATH,digest="new"))
        b["mutable_pointer_records"][-1]["source_sha256"]="new"
        self.a,self.b=a,b

    def check(self):
        a,b=report(self.a),report(self.b)
        with patch("ops.archive_custody_increment.EXPECTED_DIGEST",a["subject_sha256"]):
            return link(a,b)

    def test_link_is_deterministic_and_not_authorized(self):
        r=self.check()
        self.assertEqual(r,self.check())
        self.assertEqual(r["total_paths"],89)
        self.assertFalse(r["external_signature_verified"])
        self.assertFalse(r["hosted_archive_write_authorized"])

    def test_history_rewrite_rejected(self):
        self.b["history_records"][0]["digest"]="changed"
        with self.assertRaisesRegex(RetentionHold,"HISTORY_LINEAGE_CHANGED"):
            self.check()

    def test_archive_pointer_rewrite_rejected(self):
        self.b["mutable_pointer_records"][-1]["archive_sha256"]="changed"
        with self.assertRaisesRegex(RetentionHold,"ARCHIVE_POINTER_CHANGED"):
            self.check()

    def test_other_mutable_delta_rejected(self):
        self.b["mutable_pointer_records"][0]["new"]="changed"
        with self.assertRaisesRegex(RetentionHold,"UNEXPECTED_MUTABLE_POINTER_DELTA"):
            self.check()


if __name__=="__main__":
    unittest.main()
