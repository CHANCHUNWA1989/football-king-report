"""Synthetic, no-network S0 Pages artifact byte-level read-back regressions."""
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pages_artifact_readback import (NAMES, compare, strict_json,
                                     artifact_documents, valid_run)


def sample():
    checked = "2026-11-03T14:13:49.187906+00:00"
    return {
        "status.json": {"checked_utc": checked, "status": "RESEARCH_ONLY",
                        "production_recommendations": "DISABLED"},
        "quality.json": {"checked_utc": checked, "status": "RESEARCH_ONLY",
                         "public_matches": 165, "production_recommendations": "DISABLED"},
        "production_gate.json": {"status": "HOLD", "authenticated_forward_samples": 0,
                                 "production_recommendations": "DISABLED"},
        "market_status.json": {"status": "RESEARCH_ONLY",
                               "production_recommendations": "DISABLED"},
    }


def encoded(payload=None):
    data = sample() if payload is None else payload
    return {name: (v if isinstance(v, bytes) else json.dumps(v).encode("utf-8"))
            for name, v in data.items()}


def run():
    return {"id": 41651528536, "run_attempt": 1,
            "name": "Football King V4.1 iPhone Daily Report",
            "head_branch": "main", "event": "workflow_run",
            "status": "completed", "conclusion": "success",
            "head_sha": "e3594f8b24b92434e1e777993d4aed0699b636d2",
            "repository": {"full_name": "CHANCHUNWA1989/football-king-report"},
            "created_at": "2026-11-03T14:13:13Z",
            "updated_at": "2026-11-03T14:17:20Z"}


def build_tar(path, data, *, extra=(), add_root=True):
    with tarfile.open(path, "w") as t:
        if add_root:
            root = tarfile.TarInfo("./")
            root.type = tarfile.DIRTYPE
            t.addfile(root)
        for name, raw in list(data.items()) + list(extra):
            item = tarfile.TarInfo("./" + name)
            item.size = len(raw)
            t.addfile(item, io.BytesIO(raw))


class PagesReadbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "artifact.tar"
        self.docs = encoded()
        build_tar(self.path, self.docs)

    def check(self, *, docs=None, meta=None):
        data = self.docs if docs is None else docs
        return compare(self.path, run() if meta is None else meta,
                       fetch=lambda key: data[key])

    def test_identical_live_bytes_and_run_are_correlated_not_release(self):
        result = self.check()
        self.assertEqual(result["status"], "CONTENT_MATCHED_NOT_RELEASE_AUTHORIZATION")
        self.assertTrue(result["all_required_public_files_byte_matched"])
        self.assertEqual(set(result["matches"]), set(NAMES))
        self.assertTrue(all(row["byte_match"] for row in result["matches"].values()))
        self.assertFalse(result["deployment_commit_sha_independently_attested"])
        self.assertFalse(result["independent_reviewer_approved"])
        self.assertFalse(result["release_authorized"])
        self.assertFalse(result["verified_positive_ev"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_changed_public_document_stays_hold_even_when_semantically_equal(self):
        site = dict(self.docs)
        site["quality.json"] = json.dumps(sample()["quality.json"], indent=2).encode()
        result = self.check(docs=site)
        self.assertEqual(result["status"], "HOLD_S0_EVIDENCE_INCOMPLETE")
        self.assertFalse(result["all_required_public_files_byte_matched"])
        self.assertFalse(result["matches"]["quality.json"]["byte_match"])
        self.assertFalse(result["release_authorized"])

    def test_missing_required_archive_file_stays_hold(self):
        build_tar(self.path, {k: v for k, v in self.docs.items() if k != "quality.json"})
        self.assertIn("S0_PAGES_REQUIRED_FILES_MISSING", self.check()["reason"])

    def test_repeated_tar_member_stays_hold(self):
        build_tar(self.path, self.docs, extra=[("status.json", self.docs["status.json"])])
        self.assertIn("S0_PAGES_DUPLICATE_MEMBER", self.check()["reason"])

    def test_path_traversal_in_archive_is_rejected(self):
        build_tar(self.path, self.docs, extra=[("../escape", b"bad")])
        self.assertIn("S0_PAGES_MEMBER_PATH_UNSAFE", self.check()["reason"])

    def test_symlink_in_archive_is_rejected(self):
        with tarfile.open(self.path, "a") as t:
            info = tarfile.TarInfo("./arbitrary_link")
            info.type = tarfile.SYMTYPE
            info.linkname = "./status.json"
            t.addfile(info)
        self.assertIn("S0_PAGES_MEMBER_TYPE_UNSAFE", self.check()["reason"])

    def test_duplicate_json_keys_cannot_be_accepted(self):
        self.assertRaisesRegex(ValueError, "S0_DUPLICATE_JSON_KEY",
                               strict_json, b'{"status":"HOLD","status":"RESEARCH_ONLY"}')

    def test_nonfinite_json_cannot_be_accepted(self):
        self.assertRaisesRegex(ValueError, "S0_NONFINITE_JSON",
                               strict_json, b'{"arbitrary":NaN}')

    def test_production_toggle_is_hard_hold(self):
        docs = sample()
        docs["production_gate.json"]["production_recommendations"] = "ENABLED"
        build_tar(self.path, encoded(docs))
        self.assertIn("S0_PRODUCTION_NOT_DISABLED", self.check()["reason"])

    def test_unqualified_forward_admission_is_hard_hold(self):
        docs = sample()
        docs["production_gate.json"]["authenticated_forward_samples"] = 300
        build_tar(self.path, encoded(docs))
        self.assertIn("S0_RELEASE_GATE_WEAKENED", self.check()["reason"])

    def test_mismatched_site_clocks_are_hold(self):
        docs = sample()
        docs["quality.json"]["checked_utc"] = "2026-11-03T11:10:00Z"
        build_tar(self.path, encoded(docs))
        self.assertIn("S0_STATUS_QUALITY_CLOCK_MISMATCH", self.check()["reason"])

    def test_clock_outside_run_is_hold(self):
        docs = sample()
        docs["status.json"]["checked_utc"] = "2026-11-02T14:13:49Z"
        docs["quality.json"]["checked_utc"] = "2026-11-02T14:13:49Z"
        build_tar(self.path, encoded(docs))
        self.assertIn("S0_PAGES_CLOCK_OUTSIDE_RUN", self.check()["reason"])

    def test_run_wrong_repository_is_hold(self):
        record = run()
        record["repository"]["full_name"] = "attacker/other"
        self.assertIn("S0_WRONG_REPOSITORY", self.check(meta=record)["reason"])

    def test_run_wrong_branch_and_incomplete_status_hold(self):
        record = run()
        record["head_branch"] = "attack"
        self.assertIn("S0_UNTRUSTED_PAGES_RUN_METADATA", self.check(meta=record)["reason"])
        record = run()
        record["status"] = "in_progress"
        self.assertIn("S0_UNTRUSTED_PAGES_RUN_METADATA", self.check(meta=record)["reason"])

    def test_regular_artifact_tar_root_is_supported(self):
        raw = artifact_documents(self.path)
        self.assertEqual(raw, self.docs)


if __name__ == "__main__":
    unittest.main()
