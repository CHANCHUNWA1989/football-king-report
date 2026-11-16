"""No-network, synthetic-only tests for one real OpenLigaDB research original.

The real publisher original is tested SEPARATELY in an isolated runner; the
default GitHub CI never downloads OpenLigaDB result bytes.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ops.vnext_openligadb_offline_original import (
    OFFICIAL_JSON_SHA256,
    OFFICIAL_BYTES,
    MATCH_ID,
    _parse_structured_result,
    review_historical_original,
)


def fake_match():
    return {
        "matchID": MATCH_ID,
        "matchIsFinished": True,
        "matchDateTimeUTC": "2026-08-28T18:30:00Z",
        "leagueSeason": 2026,
        "leagueShortcut": "bl1",
        "team1": {"teamId": 40, "teamName": "FC Bayern München"},
        "team2": {"teamId": 16, "teamName": "VfB Stuttgart"},
        "matchResults": [
            {"resultID": 127516, "resultTypeKind": "HalfTime",
             "pointsTeam1": 1, "pointsTeam2": 0},
            {"resultID": 127517, "resultTypeKind": "After90Minutes",
             "pointsTeam1": 5, "pointsTeam2": 1},
        ],
    }


def binary(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class OpenLigaDBOriginalTests(unittest.TestCase):
    def test_structured_synthetic_90_min_result_is_not_certification(self):
        x = _parse_structured_result(binary(fake_match()))
        self.assertEqual(x["home_goals"], 5)
        self.assertEqual(x["away_goals"], 1)
        self.assertEqual(x["fixture_id"], "OpenLigaDB:83156")
        self.assertEqual(x["result_type_kind"], "After90Minutes")

    def test_wrong_match_id_rejected(self):
        d = fake_match()
        d["matchID"] = 123456
        with self.assertRaisesRegex(ValueError, "MISMATCHED_PROVIDER_FIXTURE_ID"):
            _parse_structured_result(binary(d))

    def test_not_finished_fails(self):
        d = fake_match()
        d["matchIsFinished"] = False
        with self.assertRaisesRegex(ValueError, "UNFINISHED_PROVIDER_MATCH"):
            _parse_structured_result(binary(d))

    def test_halftime_only_is_not_ninety_minutes(self):
        d = fake_match()
        d["matchResults"] = d["matchResults"][:1]
        with self.assertRaisesRegex(ValueError, "MISSING_UNIQUE_90MIN_RESULT"):
            _parse_structured_result(binary(d))

    def test_duplicate_90min_result_is_rejected(self):
        d = fake_match()
        d["matchResults"].append(dict(d["matchResults"][-1]))
        with self.assertRaisesRegex(ValueError, "MISSING_UNIQUE_90MIN_RESULT"):
            _parse_structured_result(binary(d))

    def test_other_season_or_team_is_rejected(self):
        for name,value in (("leagueSeason",2025),("leagueShortcut","bl2")):
            with self.subTest(name=name):
                d=fake_match()
                d[name]=value
                with self.assertRaisesRegex(ValueError, "MISMATCHED_PROVIDER_FIXTURE"):
                    _parse_structured_result(binary(d))
        d=fake_match()
        d["team1"]["teamId"]=41
        with self.assertRaisesRegex(ValueError, "MISMATCHED_PROVIDER_FIXTURE"):
            _parse_structured_result(binary(d))

    def test_kickoff_date_conflict_is_rejected(self):
        d=fake_match()
        d["matchDateTimeUTC"]="2026-08-28T18:30:01Z"
        with self.assertRaisesRegex(ValueError, "MISMATCHED_PROVIDER_FIXTURE"):
            _parse_structured_result(binary(d))

    def test_false_90min_score_or_boolean_score_rejected(self):
        for bad in (-1, 31, True, "5", None):
            with self.subTest(score=bad):
                d=fake_match()
                d["matchResults"][-1]["pointsTeam1"]=bad
                with self.assertRaisesRegex(ValueError, "INVALID_PROVIDER_90MIN_SCORE"):
                    _parse_structured_result(binary(d))

    def test_manipulated_json_duplicate_keys_rejected(self):
        valid=binary(fake_match())
        malformed=valid.replace(b'"matchID":83156',b'"matchID":83156,"matchID":83156')
        with self.assertRaisesRegex(ValueError, "DUPLICATE_RESULT_JSON_KEY"):
            _parse_structured_result(malformed)

    def test_malicious_nan_is_rejected(self):
        d=binary(fake_match())
        d=d.replace(b'"pointsTeam1":5',b'"pointsTeam1":NaN')
        with self.assertRaisesRegex(ValueError, "NONFINITE_RESULT_JSON"):
            _parse_structured_result(d)

    def test_changed_original_bytes_or_wrong_size_fails_before_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"original.json"
            file.write_bytes(binary(fake_match()))
            x=review_historical_original(file)
            self.assertEqual(x["status"],"HOLD")
            self.assertFalse(x["source_original_sha256_verified"])
            self.assertFalse(x["publisher_identity_independently_verified"])
            self.assertEqual(x["reason"],"OFFICIAL_RESULT_ORIGINAL_BYTES_NOT_PRESENT_OR_CHANGED")

    def test_symlink_original_rejected_even_if_it_points_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=Path(tmp)/"real.json"
            original.write_bytes(binary(fake_match()))
            link=Path(tmp)/"redirected.json"
            link.symlink_to(original)
            x=review_historical_original(link)
            self.assertEqual(x["status"],"HOLD")
            self.assertEqual(x["reason"],"UNSAFE_RESULT_ORIGINAL_PATH")

    def test_fail_closed_with_missing_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            x=review_historical_original(Path(tmp)/"none.json")
            self.assertEqual(x["status"],"HOLD")
            self.assertEqual(x["certified_prospective_samples"],0)
            self.assertEqual(x["production_recommendations"],"DISABLED")

    def test_explicit_capture_facts_are_unwitnessed_not_trusted(self):
        self.assertEqual(len(OFFICIAL_JSON_SHA256),64)
        self.assertGreater(OFFICIAL_BYTES,1000)
        x=review_historical_original("/not/available")
        self.assertFalse(x["capture_time_independently_attested"])
        self.assertFalse(x["result_truth_verified"])
        self.assertFalse(x["commercial_licence_fully_cleared_for_deployment"])
        self.assertFalse(x["positive_ev_verified"])
        self.assertFalse(x["eligible_for_model_scoring"])


if __name__=="__main__":
    unittest.main()
