"""Synthetic-only private archive inventory consistency and fail-closed tests."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import inplay_private_inventory as inventory
from inplay_private_claim_replay import make_private_package
from inplay_private_local_store import save_private_package
from test_inplay_two_source_byte_packet import fixture, pair, NOW


class PrivateInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.packages = [
            make_private_package(fixture(), pair(), now=NOW),
            make_private_package(fixture(), pair(), now=NOW + timedelta(seconds=1)),
        ]
        self.digests = [hashlib.sha256(x).hexdigest() for x in self.packages]
        self.filenames = ["inplay-" + x + ".tar" for x in self.digests]

    def _save(self, count=2):
        for index in range(count):
            save_private_package(self.root, self.packages[index],
                                 now=NOW + timedelta(seconds=index))

    def _audit(self, pins=None):
        return inventory.audit_private_inventory(
            self.root, self.digests if pins is None else pins,
            now=NOW + timedelta(days=10))

    def test_two_saved_packages_replay_as_research_only(self):
        self._save()
        result = self._audit()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["verified_package_count"], 2)
        self.assertTrue(result["all_expected_packages_replayed"])
        self.assertTrue(result["local_filesystem_byte_readback_verified"])
        self.assertFalse(result["durable_storage_independently_verified"])
        self.assertFalse(result["raw_source_publisher_authenticated"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["certified_forward_samples"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertIsNone(result["recommendation"])
        self.assertEqual(len(result["inventory_sha256_unattested"]), 64)

    def test_pin_order_does_not_change_inventory_commitment(self):
        self._save()
        normal = self._audit()
        reversed_order = self._audit(list(reversed(self.digests)))
        self.assertEqual(normal["status"], "RESEARCH_ONLY")
        self.assertEqual(normal["inventory_sha256_unattested"],
                         reversed_order["inventory_sha256_unattested"])

    def test_missing_package_fails_closed(self):
        self._save(1)
        self.assertEqual(self._audit()["status"], "HOLD")

    def test_unexpected_file_fails_closed_without_deleting_it(self):
        self._save()
        unexpected = self.root / "unknown-file"
        unexpected.write_text("untrusted")
        self.assertEqual(self._audit()["status"], "HOLD")
        self.assertEqual(unexpected.read_text(), "untrusted")

    def test_wrong_pin_and_duplicate_or_unbounded_pins_rejected(self):
        self._save()
        for pins in (["0" * 64, self.digests[1]],
                     [self.digests[0], self.digests[0]], [],
                     ["../private"], [None], [True],
                     self.digests * 33, "not-a-list"):
            report = self._audit(pins)
            self.assertEqual(report["status"], "HOLD")
            self.assertFalse(report["all_expected_packages_replayed"])

    def test_tampered_contents_rejected(self):
        self._save()
        (self.root / self.filenames[0]).write_bytes(b"modified")
        self.assertEqual(self._audit()["status"], "HOLD")

    def test_symlink_collision_rejected(self):
        self._save()
        target = Path(self.temp.name) / "foreign-file"
        target.write_bytes(b"private")
        (self.root / self.filenames[0]).unlink()
        (self.root / self.filenames[0]).symlink_to(target)
        self.assertEqual(self._audit()["status"], "HOLD")
        self.assertEqual(target.read_bytes(), b"private")

    def test_hardlinked_archive_rejected(self):
        self._save()
        outside = Path(self.temp.name) / "alias"
        os.link(self.root / self.filenames[0], outside)
        self.assertEqual(self._audit()["status"], "HOLD")

    def test_unsafe_directory_and_repository_traversal_rejected(self):
        self._save()
        self.root.chmod(0o755)
        self.assertEqual(self._audit()["status"], "HOLD")
        self.root.chmod(0o700)
        (Path(self.temp.name) / ".git").mkdir()
        self.assertEqual(self._audit()["status"], "HOLD")

    def test_mutation_between_first_and_second_pass_is_rejected(self):
        self._save()
        original = inventory.private._read
        touched = [False]

        def mutate_after_read(fd, filename, maximum):
            data = original(fd, filename, maximum)
            if not touched[0]:
                touched[0] = True
                (self.root / filename).write_bytes(b"changed-between-passes")
            return data

        with patch.object(inventory.private, "_read", side_effect=mutate_after_read):
            self.assertEqual(self._audit()["status"], "HOLD")
        self.assertTrue(touched[0])

    def test_private_claims_not_leaked_in_public_report(self):
        self._save()
        result = self._audit()
        self.assertNotIn("www.fotmob", str(result))
        self.assertNotIn("www.sofascore", str(result))
        self.assertNotIn(str(self.root), str(result))
        self.assertNotIn("synthetic_event_123", str(result))

    def test_no_persistence_claim_even_after_replay(self):
        self._save()
        result = self._audit()
        for key in ("durable_storage_independently_verified",
                    "externally_witnessed", "signed_timestamp_verified",
                    "source_independence_verified", "eligible_for_model_input",
                    "eligible_for_model_scoring"):
            self.assertFalse(result[key])


if __name__ == "__main__":
    unittest.main()
