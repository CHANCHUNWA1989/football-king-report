import json
import tempfile
import unittest
from pathlib import Path
from ops.private_snapshot_archive import store, inspect


def forecast():
    return {"fixture_id": "synthetic-1", "model": "poisson", "model_version": "test-v1",
            "prediction_utc": "2026-01-01T10:00:00Z",
            "kickoff_utc": "2026-01-01T12:00:00Z",
            "probabilities": {"H": 0.5, "D": 0.3, "A": 0.2},
            "production_recommendations": "DISABLED"}


class ArchiveTests(unittest.TestCase):
    def test_exclusive_write_and_read(self):
        with tempfile.TemporaryDirectory() as root:
            receipt = store(root, forecast())
            self.assertTrue(receipt["archive_written"])
            self.assertFalse(receipt["capture_time_independently_attested"])
            self.assertTrue(inspect(root, receipt["sha256"])["sha256"])
            with self.assertRaises(ValueError):
                store(root, forecast())

    def test_modified_entry_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            receipt = store(root, forecast())
            path = Path(root) / (receipt["sha256"] + ".json")
            data = json.loads(path.read_text())
            data["forecast"]["probabilities"] = {"H": 0.6, "D": 0.2, "A": 0.2}
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                inspect(root, receipt["sha256"])

    def test_invalid_digest_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                inspect(root, "../etc/passwd")

    def test_symlink_directory_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            link = Path(root) / "link"
            link.symlink_to(Path(root), target_is_directory=True)
            with self.assertRaises(ValueError):
                store(link, forecast())


if __name__ == "__main__":
    unittest.main()
