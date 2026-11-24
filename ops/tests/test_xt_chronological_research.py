"""Synthetic, stdlib-only regressions for 12+4 historical xT research gate.

NO provider match files, third-party model fitting or package installation
in GitHub CI. The real installed Socceraction model smoke is separate.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from ops import xt_chronological_research as xt


MANIFEST = (Path(__file__).resolve().parents[1] / "research_manifests" /
            "statsbomb_wc2022_xt_12train_4eval_20261115.json")


class XTChronologicalResearchGateTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def evaluate(self):
        return xt.validate_manifest(self.manifest)

    def test_exact_immutable_historical_manifest_and_time_embargo(self):
        train, heldout = self.evaluate()
        self.assertEqual(len(train), 12)
        self.assertEqual(len(heldout), 4)
        self.assertEqual(tuple(m["match_id"] for m in train), xt.TRAIN_IDS)
        self.assertEqual(tuple(m["match_id"] for m in heldout), xt.EVAL_IDS)
        self.assertLess(max(m["match_date"] for m in train), xt.EMBARGO.isoformat())
        self.assertGreater(min(m["match_date"] for m in heldout), xt.EMBARGO.isoformat())
        self.assertEqual(self.manifest["source_commit"], xt.SOURCE_COMMIT)

    def test_eval_match_cannot_be_swapped_into_training_set(self):
        self.manifest["train"][0]["match_id"] = xt.EVAL_IDS[0]
        with self.assertRaisesRegex(ValueError, "MATCH_ID_SPLIT_CONTAMINATION"):
            self.evaluate()

    def test_training_match_cannot_be_pushed_into_holdout(self):
        self.manifest["eval"][0]["match_id"] = xt.TRAIN_IDS[0]
        with self.assertRaisesRegex(ValueError, "MATCH_ID_SPLIT_CONTAMINATION"):
            self.evaluate()

    def test_embargo_or_split_boundary_cannot_be_shortened(self):
        for field, changed in (("embargo_dates", []),
                               ("train_through", "2022-11-25"),
                               ("eval_from", "2022-11-23")):
            with self.subTest(field=field):
                doc = deepcopy(self.manifest)
                doc[field] = changed
                with self.assertRaisesRegex(ValueError, "SOURCE_OR_TIME_BOUNDARY_MISMATCH"):
                    xt.validate_manifest(doc)

    def test_train_match_on_or_after_embargo_fails(self):
        self.manifest["train"][-1]["match_date"] = "2022-11-24"
        with self.assertRaisesRegex(ValueError, "CHRONOLOGICAL_LEAKAGE"):
            self.evaluate()

    def test_eval_match_pre_embargo_fails(self):
        self.manifest["eval"][0]["match_date"] = "2022-11-23"
        with self.assertRaisesRegex(ValueError, "CHRONOLOGICAL_LEAKAGE"):
            self.evaluate()

    def test_reordered_training_match_dates_fail(self):
        self.manifest["train"][0]["match_date"] = "2022-11-23"
        with self.assertRaisesRegex(ValueError, "UNSORTED_MATCH_CHRONOLOGY"):
            self.evaluate()

    def test_reordered_intra_day_kickoff_fails(self):
        self.manifest["eval"][0]["kick_off"] = "20:00:00.000"
        with self.assertRaisesRegex(ValueError, "UNSORTED_MATCH_CHRONOLOGY"):
            self.evaluate()

    def test_missing_hash_and_invalid_byte_size_fail_closed(self):
        for field,value in (("sha256", "0"*63), ("bytes", 0), ("records", -4)):
            with self.subTest(field=field):
                document = deepcopy(self.manifest)
                document["train"][0]["events"][field] = value
                with self.assertRaises(ValueError):
                    xt.validate_manifest(document)

    def test_foreign_upstream_commit_or_match_index_is_rejected(self):
        for key in ("source_repo", "source_commit", "match_index_sha256"):
            with self.subTest(key=key):
                document = deepcopy(self.manifest)
                document[key] = "forged-source"
                with self.assertRaisesRegex(ValueError, "SOURCE_OR_TIME_BOUNDARY_MISMATCH"):
                    xt.validate_manifest(document)

    def test_swapped_team_or_duplicate_team_ids_not_accepted(self):
        self.manifest["train"][0]["away_team_id"] = self.manifest["train"][0]["home_team_id"]
        with self.assertRaisesRegex(ValueError, "INVALID_MATCH_TEAMS"):
            self.evaluate()

    def test_extra_or_missing_match_is_rejected(self):
        for key in ("train", "eval"):
            with self.subTest(key=key):
                doc = deepcopy(self.manifest)
                doc[key].pop()
                with self.assertRaisesRegex(ValueError, "MATCH_ID_SPLIT_CONTAMINATION"):
                    xt.validate_manifest(doc)

    def test_local_source_file_must_match_exact_bytes_and_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"events.json"
            p.write_bytes(b"original")
            item={"bytes":8,"sha256":sha256(b"original").hexdigest()}
            self.assertEqual(xt._read_source(p,item),b"original")
            p.write_bytes(b"tampered")  # same size as 'original'
            with self.assertRaisesRegex(ValueError, "HISTORICAL_SOURCE_SHA256_MISMATCH"):
                xt._read_source(p,item)

    def test_symlink_or_missing_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            original=Path(d)/"original.json"
            link=Path(d)/"event.json"
            original.write_bytes(b"real")
            link.symlink_to(original)
            item={"bytes":4,"sha256":sha256(b"real").hexdigest()}
            with self.assertRaisesRegex(ValueError, "MISSING_OR_CHANGED_HISTORICAL_SOURCE"):
                xt._read_source(link,item)
            with self.assertRaisesRegex(ValueError, "MISSING_OR_CHANGED_HISTORICAL_SOURCE"):
                xt._read_source(Path(d)/"no.json",item)

    def test_only_all_32_verified_provider_files_can_progress(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(xt, "_read_source", return_value=b"mock-validated") as verify:
                files=xt.verify_all_historical_sources(root,self.manifest)
            self.assertEqual(len(files),16)
            self.assertEqual(verify.call_count,32)
            self.assertEqual(set(files),set(xt.TRAIN_IDS+xt.EVAL_IDS))

    def test_extra_or_missing_frozen_data_never_enters_model_fit(self):
        with patch.object(xt, "_versions") as versions:
            with self.assertRaisesRegex(ValueError, "UNVERIFIED_MATCH_SOURCE_COVERAGE"):
                xt.fit_and_rate_historical_xt(self.manifest,{})
            versions.assert_not_called()

    def test_wrong_optional_dependency_version_fails_closed(self):
        with patch.object(xt.metadata,"version",side_effect=lambda n:"999.0"):
            with self.assertRaisesRegex(ValueError, "OPTIONAL_XT_DEPENDENCY_VERSION_MISMATCH"):
                xt._versions()

    def test_coordinate_or_timestamp_spoof_rejected_before_model(self):
        sample=self.manifest["train"][0]
        good=[
            {"game_id":sample["match_id"],"action_id":0,"team_id":sample["home_team_id"],
             "period_id":1,"time_seconds":1.0,"start_x":22.0,"end_x":30.0,
             "start_y":31.0,"end_y":30.0,"type_name":"pass"},
            {"game_id":sample["match_id"],"action_id":1,"team_id":sample["away_team_id"],
             "period_id":1,"time_seconds":2.0,"start_x":27.0,"end_x":29.0,
             "start_y":20.0,"end_y":22.0,"type_name":"dribble"},
        ]
        self.assertEqual(xt.summarize_spadl_rows_for_match(good,sample),2)
        for key,bad,msg in (("start_x",105.1,"INVALID_ACTION_COORDINATES"),
                            ("time_seconds",float("nan"),"INVALID_ACTION_CLOCK"),
                            ("game_id",999,"CROSS_MATCH_OR_ACTION_ID")):
            with self.subTest(key=key):
                altered=deepcopy(good)
                altered[0][key]=bad
                with self.assertRaisesRegex(ValueError,msg):
                    xt.summarize_spadl_rows_for_match(altered,sample)


if __name__=="__main__":
    unittest.main()
