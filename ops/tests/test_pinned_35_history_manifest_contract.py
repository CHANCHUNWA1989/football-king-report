"""Pin the actual 35-path GitHub gzip manifest's research-only contract.

No network, hosted archive writes, checkout modifications or authority claims.
The original bytes were read at an exact GitHub source commit; these tests
guard the manifest metadata against silent drift, not archived-copy parity.
"""

from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
import unittest

from ops.history_blob_retention_preflight import RetentionHold, _validate


MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "docs/P0_569_PINNED_35_HISTORY_BLOBS_SHA256_2026_11_24.json"
)
PINNED_MAIN = "12155d9058a3709ccd0333bb103bbb8cce0e3cec"
PINNED_ARCHIVE_BASE = "3ce493fbeb9bfea29af1b93064a085afe8efb280"


class Pinned35GzipManifestContractTests(unittest.TestCase):
    def setUp(self):
        self.original = MANIFEST.read_bytes()
        self.doc = json.loads(self.original)

    def tearDown(self):
        self.assertEqual(MANIFEST.read_bytes(), self.original)

    def test_real_pinned_manifest_complete_and_never_deployed(self):
        d = self.doc
        self.assertEqual(d["source_main_sha"], PINNED_MAIN)
        self.assertEqual(d["archive_bootstrap_sha"], PINNED_ARCHIVE_BASE)
        self.assertEqual(d["source_added_gzip_paths"], 35)
        self.assertEqual(d["source_unique_git_blobs"], 22)
        self.assertEqual(d["compressed_bytes_sum"], 124600)
        self.assertEqual(d["production_recommendations"], "DISABLED")
        self.assertIs(d["remote_archive_copy_confirmed"], False)
        self.assertIs(d["independent_archive_retention_verified"], False)
        self.assertIs(d["main_ruleset_activation_authorized"], False)
        self.assertIs(d["source_github_git_tree_truncated"], False)
        self.assertEqual(len(_validate(d)), 35)
        paths = [r["path"] for r in d["records"]]
        self.assertEqual(paths, sorted(set(paths)))
        self.assertEqual(sum(row["compressed_bytes"] for row in d["records"]), 124600)

    def test_all_seven_history_families_are_explicitly_preserved(self):
        paths = [r["path"] for r in self.doc["records"]]
        expected = {
            "forecast_provenance/": 20,
            "history/": 2,
            "research_pairs/": 2,
            "shadow/": 2,
            "verification_slates/": 2,
            "worldwide_shadow/": 2,
            "sources/": 5,
        }
        for prefix, n in expected.items():
            self.assertEqual(sum(path.startswith(prefix) for path in paths), n)
        self.assertEqual(sum(expected.values()), 35)
        self.assertTrue(all(path.endswith(".gz") for path in paths))

    def test_same_git_blob_always_has_same_sha256_and_size(self):
        groups = defaultdict(set)
        for r in self.doc["records"]:
            groups[r["git_blob_sha1"]].add(
                (r["sha256_compressed"], r["compressed_bytes"]))
        self.assertEqual(len(groups), 22)
        self.assertTrue(all(len(v) == 1 for v in groups.values()))
        self.assertEqual(
            next(r["sha256_compressed"] for r in self.doc["records"]
                 if r["path"].endswith("/45186921642-1/negative_checks.json.gz")),
            "5072b0810905e4e9b57e1bbafb9678ec6256dd1745017586c7ad572680cd4fa0",
        )

    def test_manifest_safety_promotion_and_digest_edit_fail_closed(self):
        for change in (
            {"remote_archive_copy_confirmed": True},
            {"independent_archive_retention_verified": True},
            {"main_ruleset_activation_authorized": True},
            {"production_recommendations": "ENABLED"},
            {"source_github_git_tree_truncated": True},
            {"source_unique_git_blobs": 21},
            {"compressed_bytes_sum": 124599},
        ):
            with self.subTest(change=change):
                changed = deepcopy(self.doc)
                changed.update(change)
                with self.assertRaises(RetentionHold):
                    _validate(changed)


if __name__ == "__main__":
    unittest.main()
