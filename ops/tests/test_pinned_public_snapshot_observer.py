"""Pinned snapshot observer: offline fixtures, no network, no site changes."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest

from ops.pinned_public_snapshot_observer import (
    DOCS, MANIFEST, SnapshotHold, compare_trees, observe, _read_document, _tree,
)


class PinnedPublicSnapshotObserverTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2]
        self.manifest = json.loads((root / MANIFEST).read_bytes())
        self.src = self.manifest["source_main_sha"]
        self.dst = self.manifest["archive_bootstrap_sha"]
        self.src_tree, self.dst_tree = "1" * 40, "2" * 40
        self.source_rows = {
            r["path"]: {"path": r["path"], "mode": "100644", "type": "blob",
                         "sha": r["git_blob_sha1"], "size": r["compressed_bytes"]}
            for r in self.manifest["records"]
        }
        self.target_rows = {}
        self.responses = {}
        for path in DOCS:
            raw = (root / path).read_bytes()
            oid = hashlib.sha1(
                b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
            ).hexdigest()
            self.source_rows[path] = {"path": path, "mode": "100644",
                                      "type": "blob", "sha": oid, "size": len(raw)}
            self.responses["/git/blobs/" + oid] = {
                "sha": oid, "encoding": "base64",
                "content": base64.b64encode(raw).decode("ascii"),
            }
        self.now = datetime(2026, 11, 24, tzinfo=timezone.utc)
        self.requests = []

    def get(self, endpoint, limit):
        self.requests.append(endpoint)
        for commit, tree_sha, rows in (
            (self.src, self.src_tree, self.source_rows),
            (self.dst, self.dst_tree, self.target_rows),
        ):
            if endpoint == "/git/commits/" + commit:
                return {"sha": commit, "tree": {"sha": tree_sha}}
            if endpoint == "/git/trees/" + tree_sha + "?recursive=1":
                return {"sha": tree_sha, "truncated": False,
                        "tree": list(rows.values())}
        return self.responses[endpoint]

    def test_pinned_manifest_missing_target_and_actual_local_builder_baseline(self):
        report = observe(self.manifest, get=self.get, now=self.now)
        h = report["history"]
        self.assertEqual(h["source_manifest_tree_entries_matched"], 35)
        self.assertEqual(h["target_missing_paths"], 35)
        self.assertEqual(h["target_git_blob_identity_matches"], 0)
        self.assertFalse(h["target_raw_sha256_readback_performed"])
        self.assertGreaterEqual(report["pinned_real_research_rows"], 105)
        self.assertEqual(report["official_readiness_rows_same_input"],
                         report["daily_scorecard_rows_same_input"])
        self.assertEqual(report["independently_verified_result_cases"], 0)
        self.assertFalse(report["hosted_archive_retention_attested"])
        self.assertFalse(report["site_published"])
        self.assertFalse(report["source_switch_authorized"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(len(self.requests), 7)

    def test_matching_tree_metadata_alone_never_proves_raw_readback(self):
        result = compare_trees(self.manifest, self.source_rows, self.source_rows)
        self.assertEqual(result["target_git_blob_identity_matches"], 35)
        self.assertFalse(result["target_raw_sha256_readback_performed"])

    def test_changed_and_symlinked_targets_are_not_matching(self):
        paths = sorted(self.source_rows)
        historical = [x for x in paths if x.endswith(".gz")]
        a, b, c = historical[:3]
        target = {x: deepcopy(self.source_rows[x]) for x in (a, b, c)}
        target[b]["sha"] = "9" * 40
        target[c]["mode"] = "120000"
        result = compare_trees(self.manifest, self.source_rows, target)
        self.assertEqual(result["target_git_blob_identity_matches"], 1)
        self.assertEqual(result["target_different_paths"], 2)
        self.assertEqual(result["target_missing_paths"], 32)

    def test_source_manifest_mismatch_fails_closed(self):
        path = self.manifest["records"][0]["path"]
        self.source_rows[path]["size"] += 1
        with self.assertRaisesRegex(SnapshotHold, "SOURCE_TREE_MANIFEST_MISMATCH"):
            compare_trees(self.manifest, self.source_rows, self.target_rows)

    def test_truncated_tree_and_wrong_commit_rejected(self):
        def truncated(endpoint, limit):
            value = self.get(endpoint, limit)
            if "/trees/" in endpoint:
                value["truncated"] = True
            return value
        with self.assertRaisesRegex(SnapshotHold, "SNAPSHOT_TREE_INCOMPLETE"):
            _tree(self.src, truncated)
        def wrong(endpoint, limit):
            value = self.get(endpoint, limit)
            if "/commits/" in endpoint:
                value["sha"] = self.dst
            return value
        with self.assertRaisesRegex(SnapshotHold, "SNAPSHOT_COMMIT_MISMATCH"):
            _tree(self.src, wrong)

    def test_raw_document_git_blob_identity_is_checked(self):
        path = DOCS[0]
        endpoint = "/git/blobs/" + self.source_rows[path]["sha"]
        self.responses[endpoint]["content"] = base64.b64encode(
            b'{"production_recommendations":"DISABLED"}').decode("ascii")
        with self.assertRaisesRegex(SnapshotHold, "SNAPSHOT_BLOB_CONTENT_MISMATCH"):
            _read_document(self.source_rows, path, self.get)


if __name__ == "__main__":
    unittest.main()
