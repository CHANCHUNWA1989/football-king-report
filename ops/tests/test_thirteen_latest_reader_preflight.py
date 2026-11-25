"""Local Git fixtures for fixed status pointer contracts; no hosted writes."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from ops.thirteen_latest_reader_preflight import CONTRACTS, inspect, read_pinned
from ops.six_latest_reader_preflight import LatestReadHold
from ops.archive_hosted_write_lock import require_independent_hosted_archive_custody, HostedArchiveWriteHold


class ThirteenLatestReaderTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.DEVNULL).decode().strip()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fk-thirteen-pointers-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init")
        self.git("config", "user.name", "fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.write_all("2026-11-23T00:00:00Z")
        self.archive = self.commit()
        self.write_all("2026-11-24T00:00:00Z")
        self.source = self.commit()
        self.now = "2026-11-24T12:00:00Z"

    def write_all(self, clock):
        for path, (schema, key, _, flags, status_key, statuses) in CONTRACTS.items():
            p = self.root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {"schema": schema, key: clock, status_key: statuses[0],
                    "production_recommendations": "DISABLED", **flags}
            if path == "sources/research_extensions_latest.json":
                data["started_utc"] = clock
            p.write_text(json.dumps(data))

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def test_exact_13_read_and_stale_is_not_release(self):
        result = inspect(self.root, self.source, self.archive, self.archive, self.now)
        self.assertEqual(result["compatible_count"], 13)
        self.assertGreater(result["stale_count"], 0)
        self.assertTrue(result["six_league_timestamp_consistent"])
        self.assertFalse(result["source_switch_authorized"])
        self.assertFalse(result["hosted_archive_write_authorized"])
        self.assertFalse(result["tradable_market_freshness_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_candidate_cannot_replace_mutable_archive_pointers(self):
        result = inspect(self.root, self.source, self.archive, self.source, self.now)
        self.assertEqual(result["compatible_count"], 0)

    def test_invalid_safety_value_and_dirty_checkout(self):
        name = "market/private_summary_latest.json"
        p = self.root / name
        data = json.loads(p.read_text())
        data["verified_bets"] = False
        p.write_text(json.dumps(data))
        # Pinned reads ignore dirty worktree; committed wrong type is rejected.
        self.assertEqual(inspect(self.root, self.source, self.archive, self.archive, self.now)["compatible_count"], 13)
        changed = self.commit()
        self.assertEqual(inspect(self.root, changed, self.archive, self.archive, self.now)["compatible_count"], 12)

    def test_missing_pointer_and_unapproved_path(self):
        (self.root / "market/collection_status.json").unlink()
        changed = self.commit()
        self.assertEqual(inspect(self.root, changed, self.archive, self.archive, self.now)["compatible_count"], 12)
        with self.assertRaises(LatestReadHold):
            read_pinned(self.root, self.source, ".git/config")

    def test_six_league_split_not_authorized(self):
        p = self.root / "sources/seven_quality_gates_latest.json"
        doc = json.loads(p.read_text())
        doc["captured_utc"] = "2026-11-24T01:00:00Z"
        p.write_text(json.dumps(doc))
        changed = self.commit()
        result = inspect(self.root, changed, self.archive, self.archive, self.now)
        self.assertFalse(result["six_league_timestamp_consistent"])
        self.assertFalse(result["source_switch_authorized"])

    def test_hosted_lock_remains_unconditional(self):
        with self.assertRaises(HostedArchiveWriteHold):
            require_independent_hosted_archive_custody()


if __name__ == "__main__":
    unittest.main()
