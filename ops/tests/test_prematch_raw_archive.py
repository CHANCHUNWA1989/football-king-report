"""Raw odds evidence corruption and symlink failure tests."""
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prematch_raw_archive import archive_response, replay_response


class TestRawArchive(unittest.TestCase):
    def test_replay_and_corruption(self):
        with tempfile.TemporaryDirectory() as root:
            saved = archive_response(b'{"odds": [2, 3, 4]}', directory=root)
            self.assertEqual(replay_response(saved["path"],
                             expected_sha256=saved["sha256"]), b'{"odds": [2, 3, 4]}')
            Path(saved["path"]).write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                replay_response(saved["path"], expected_sha256=saved["sha256"])
            with self.assertRaises(ValueError):
                archive_response(b'{"odds": [2, 3, 4]}', directory=root)

    def test_missing_directory_and_invalid_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                archive_response(b"", directory=root)
            with self.assertRaises(ValueError):
                archive_response(b"x", directory=Path(root) / "missing")
            with self.assertRaises(ValueError):
                archive_response(b"x" * 1_000_001, directory=root)

    def test_symlink_replay_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            saved = archive_response(b"raw", directory=root)
            link = Path(root) / "link.json"
            link.symlink_to(saved["path"])
            with self.assertRaises(ValueError):
                replay_response(link, expected_sha256=saved["sha256"])


if __name__ == "__main__":
    unittest.main()
