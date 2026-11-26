"""Phase 10 nofollow archive replay adversarial regression."""
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prematch_raw_archive import archive_response, replay_response


class TestArchiveInodeSafety(unittest.TestCase):
    def test_symlink_replay_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            raw = b"example"
            digest = hashlib.sha256(raw).hexdigest()
            original = Path(root) / "source"
            original.write_bytes(raw)
            linked = Path(root) / (digest + ".json")
            linked.symlink_to(original)
            with self.assertRaises((OSError, ValueError)):
                replay_response(linked, expected_sha256=digest)

    def test_hardlinked_archive_replay_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            archive = archive_response(b"example", directory=root)
            os.link(archive["path"], Path(root) / "extra-link")
            with self.assertRaises(ValueError):
                replay_response(archive["path"], expected_sha256=archive["sha256"])

    def test_regular_archive_replay_succeeds(self):
        with tempfile.TemporaryDirectory() as root:
            archive = archive_response(b"example", directory=root)
            self.assertEqual(replay_response(archive["path"],
                             expected_sha256=archive["sha256"]), b"example")


if __name__ == "__main__":
    unittest.main()
