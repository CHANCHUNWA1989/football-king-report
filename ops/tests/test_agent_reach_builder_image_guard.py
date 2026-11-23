"""Synthetic acceptance and fail-closed tests for Docker builder image lock."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_reach_builder_image_guard import (
    ImageHold, SCHEMA, acceptance, immutable_reference, read_manifest,
)

GOOD = {
    "schema": SCHEMA,
    "repository": "docker.io/library/python",
    "observed_tag": "3.12-slim",
    "platform": "linux/amd64",
    "digest": "sha256:" + "a" * 64,
}


class BuilderImageGuardTests(unittest.TestCase):
    def test_accepts_only_repository_digest_not_tag(self):
        self.assertEqual(
            immutable_reference(GOOD),
            "docker.io/library/python@sha256:" + "a" * 64,
        )
        self.assertNotIn(":3.12-slim@", immutable_reference(GOOD))

    def test_no_betting_promotion_possible(self):
        v = acceptance()
        self.assertEqual(v["status"], "HOLD")
        self.assertEqual(v["production_recommendations"], "DISABLED")
        self.assertFalse(v["publisher_signature_verified"])
        self.assertFalse(v["host_egress_firewall_verified"])
        self.assertFalse(v["registry_digest_download_independently_verified_by_this_parser"])
        self.assertFalse(v["source_timestamp_attested"])
        self.assertFalse(v["eligible_for_model"])
        self.assertIsNone(v["verified_positive_ev"])

    def test_rejects_moving_tag_or_wrong_repository(self):
        for changed in (
            {"repository": "evil.example/library/python"},
            {"repository": "python"},
            {"observed_tag": "latest"},
            {"observed_tag": "3.12"},
        ):
            with self.subTest(changed=changed), self.assertRaises(ImageHold):
                immutable_reference({**GOOD, **changed})

    def test_rejects_invalid_or_non_linux_amd64_platform(self):
        for platform in ("linux/arm64", "linux/386", "", None, "linux/amd64;echo fake"):
            with self.subTest(platform=platform), self.assertRaises(ImageHold):
                immutable_reference({**GOOD, "platform": platform})

    def test_rejects_bad_digest_and_injection(self):
        for digest in (
            "sha256:" + "g" * 64,
            "sha256:" + "a" * 63,
            "sha256:" + "A" * 64,
            "sha256:" + "a" * 64 + "; echo untrusted",
            "latest",
            "sha256:" + "a" * 65,
            None,
        ):
            with self.subTest(digest=digest), self.assertRaises(ImageHold):
                immutable_reference({**GOOD, "digest": digest})

    def test_rejects_bare_manifest_and_unknown_keys(self):
        for bad in (
            None, "", {}, {"digest": GOOD["digest"]},
            {**GOOD, "approved_for_wagers": True},
            {**GOOD, "schema": "v9"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ImageHold):
                immutable_reference(bad)

    def test_does_not_mutate_approved_manifest(self):
        a = copy.deepcopy(GOOD)
        immutable_reference(a)
        self.assertEqual(a, GOOD)

    def test_read_manifest_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "valid.json"
            target.write_text(json.dumps(GOOD), encoding="utf-8")
            link = root / "redirect.json"
            link.symlink_to(target)
            with self.assertRaises(ImageHold):
                read_manifest(link)

    def test_manifest_file_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "oversized.json"
            p.write_bytes(b"x" * 5000)
            with self.assertRaises(ImageHold):
                read_manifest(p)


if __name__ == "__main__":
    unittest.main()
