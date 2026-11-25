"""P0 stage 4: isolated local Git writer -> pinned reader -> both mobile builders.
Legacy research records are real checked-in bytes; all appended rows are synthetic.
Never uses hosted writes, live provider results, or production recommendations.
"""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from ops.isolated_provenance_archive import ARCHIVE_REF
from ops.isolated_settlement_archive import append
from ops.isolated_settlement_bridge import BridgeHold, reconcile
from ops.mobile_shared_settlement import _assemble
from ops.settled_archive_request import request_body
from ops.tests.test_four_writer_shared_archive_canary import FourWriterSharedArchiveCanaryTests, git


class P0ArchiveIntegratedReplayTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.case = FourWriterSharedArchiveCanaryTests(
            "test_all_four_writers_commit_15_exact_gzip_blobs_to_one_archive")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.original = (self.root / "evidence/settled.json").read_bytes()
        self.legacy = json.loads(self.original)
        self.case.legacy.write_bytes(self.original)
        self.case.legacy_bytes = self.original
        self.case.provision()
        self.gates = json.loads((self.root / "sources/seven_quality_gates_latest.json").read_bytes())
        self.market = json.loads((self.root / "market/latest.json").read_bytes())

    def batch(self, start, count):
        rows = []
        for i in range(start, start + count):
            row = deepcopy(self.legacy["samples"][0])
            row["key"] = "synthetic/p0-stage4/" + str(i)
            row["fixture_result_source_independently_verified"] = False
            row["production_recommendations"] = "DISABLED"
            # Force a large request without changing sealed vectors.
            row["synthetic_test_padding"] = "x" * 2000
            rows.append(row)
        return dict(self.legacy, samples=rows, n=len(rows))

    def test_bulk_writer_reader_file_request_and_both_mobile_builders(self):
        self.case.incoming.write_text(json.dumps(self.batch(0, 23)))
        receipts = self.case.append_all()
        self.assertEqual(sum(r["new_files"] for r in receipts.values()), 15)
        sha = self.case.full_readback()
        merged, receipt = reconcile(self.case.legacy, self.case.reader, sha)
        self.assertEqual(receipt["new_samples"], 23)
        self.assertEqual(merged["n"], self.legacy["n"] + 23)
        self.assertEqual(merged["samples"][:self.legacy["n"]], self.legacy["samples"])
        raw = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode()
        old_sha = hashlib.sha1(b"blob " + str(len(self.original)).encode() + b"\0" + self.original).hexdigest()
        payload = request_body(raw, old_sha)
        self.assertGreater(len(payload["content"]), 131072)
        self.assertEqual(base64.b64decode(payload["content"], validate=True), raw)
        self.assertEqual(payload["sha"], old_sha)
        # Serialize only; no API PUT. This compatibility payload targets main,
        # while the isolated writer above uses the fixed local archive ref.
        path = self.case.legacy.parent / "request.json"
        path.write_text(json.dumps(payload))
        self.assertEqual(base64.b64decode(json.loads(path.read_text())["content"]), raw)
        preview = _assemble(self.legacy, merged, receipt, self.gates, self.market)
        self.assertEqual(preview["official_readiness_samples"], merged["n"])
        self.assertEqual(preview["daily_scorecard_samples"], merged["n"])
        self.assertFalse(preview["source_switch_authorized"])
        self.assertFalse(preview["verified_final_scores"])
        self.assertEqual(preview["production_recommendations"], "DISABLED")
        self.assertEqual(self.case.append("settlement")["status"], "ALREADY_ARCHIVED")
        self.assertEqual(self.case.remote_head(ARCHIVE_REF), sha)
        self.case.assert_main_unchanged()

    def test_missing_one_of_two_committed_batches_is_rejected(self):
        self.case.incoming.write_text(json.dumps(self.batch(0, 1)))
        self.case.append("settlement")
        self.case.incoming.write_text(json.dumps(self.batch(1, 1)))
        append(self.case.incoming, self.case.legacy, self.case.writer,
               "9010", "1", self.case.DAY, max_tries=1)
        sha = self.case.full_readback()
        merged, receipt = reconcile(self.case.legacy, self.case.reader, sha)
        self.assertEqual(receipt["new_samples"], 2)
        (self.case.reader / f"settlement_batches/{self.case.DAY}/9010-1.json.gz").unlink()
        self.assertEqual(git(self.case.reader, "rev-parse", "HEAD"), sha)
        with self.assertRaisesRegex(BridgeHold, "COMMITTED_SETTLEMENT_BATCH_MISSING"):
            reconcile(self.case.legacy, self.case.reader, sha)
        self.case.assert_main_unchanged()


if __name__ == "__main__":
    unittest.main()
