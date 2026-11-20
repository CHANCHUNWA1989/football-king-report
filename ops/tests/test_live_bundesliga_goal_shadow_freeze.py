import copy
from datetime import datetime, timezone
import unittest

from ops.live_bundesliga_goal_shadow_freeze import build_live_input
from ops.forward_goal_shadow_cohort_seal import build, verify

NOW = datetime(2026, 11, 16, 15, 30, tzinfo=timezone.utc)
RECEIVED = datetime(2026, 11, 16, 15, 20, tzinfo=timezone.utc)
COMPUTED = datetime(2026, 11, 16, 15, 25, tzinfo=timezone.utc)
SHA = "e466196956a0780776bc90ef1168f6c462024c3e"


def source():
    raw = "a" * 64
    rows = [
        {"status": "FINISHED", "date": "2026-11-14",
         "kickoff_utc": "2026-11-14T14:00:00Z",
         "home": f"H{i}", "away": f"A{i}", "score_ft": [i % 4, i % 3]}
        for i in range(36)
    ]
    for mid, kickoff in ((10001, "2026-11-21T12:30:00Z"),
                         (10002, "2026-11-21T14:30:00Z")):
        rows.append({
            "status": "SCHEDULED",
            "date": "2026-11-21",
            "event_id": f"openligadb:{mid}", "kickoff_utc": kickoff,
            "score_ft": None,
            "_same_response_native_fixture_input": {
                "match_id": mid, "home_team_id": mid*2,
                "away_team_id": mid*2+1,
                "league_shortcut": "bl1",
                "source_response_sha256": raw,
            },
        })
    return {"status": "READY_RESEARCH", "source": "OpenLigaDB",
            "league": "bundesliga", "season": "2026-27",
            "matches": rows, "_same_response_source_sha256": raw,
            "sha256": raw}


def forecasts():
    return [{
        "event_id": "openligadb:10001",
        "kickoff_utc": "2026-11-21T12:30:00Z",
        "expected_home_goals": 1.8,
        "expected_away_goals": 1.0,
    }]


def gather(s=None, p=None):
    return build_live_input(
        s if s is not None else source(), p if p is not None else forecasts(),
        source_received=RECEIVED, model_computed=COMPUTED,
        model_sha=SHA, season="2026-27", run_id="github-actions:123:1")


class LiveBundesligaGoalFreezeTests(unittest.TestCase):
    def test_same_get_future_capture_preserves_unforecast_match(self):
        p = gather()
        self.assertEqual(len(p["fixtures"]), 2)
        self.assertEqual(len(p["forecasts"]), 1)
        self.assertEqual(p["training"]["training_match_count"], 36)
        self.assertEqual(p["source"]["source_response_sha256"], "a"*64)
        saved = build(p, now=NOW)
        self.assertTrue(verify(saved))
        self.assertEqual(saved["payload"]["missing_forecasts_included_as_holds"], 1)
        self.assertEqual(saved["payload"]["production_recommendations"], "DISABLED")

    def test_no_lookahead_outcomes_change_model_rates(self):
        x = source()
        y = copy.deepcopy(x)
        for r in y["matches"]:
            if r["status"] == "FINISHED":
                r["score_ft"] = [0, 0]
        pa = gather(x)
        pb = gather(y)
        self.assertNotEqual(pa["training"]["over25_frequency"],
                            pb["training"]["over25_frequency"])
        self.assertEqual(pa["forecasts"], pb["forecasts"])

    def test_reject_future_score_inserted_into_scheduled_row(self):
        s = source()
        s["matches"][-1]["score_ft"] = [4, 0]
        with self.assertRaisesRegex(ValueError, "SCHEDULED_SOURCE_ROW_CONTAINS_RESULT"):
            gather(s)

    def test_reject_missing_native_match_id_or_mismatch(self):
        s = source()
        s["matches"][-1]["_same_response_native_fixture_input"] = None
        with self.assertRaisesRegex(ValueError, "SCHEDULED_NATIVE_FIXTURE"):
            gather(s)
        s = source()
        s["matches"][-1]["event_id"] = "openligadb:999"
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_CONFLICTING"):
            gather(s)

    def test_reject_duplicate_fixtures_or_history_conflicts(self):
        s = source()
        s["matches"].append(copy.deepcopy(s["matches"][-1]))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_CONFLICTING_SCHEDULED_FIXTURE"):
            gather(s)
        s = source()
        s["matches"].append({**s["matches"][0], "score_ft": [9, 9]})
        with self.assertRaisesRegex(ValueError, "CONFLICTING_SOURCE_HISTORICAL_SCORE"):
            gather(s)

    def test_reject_unsafe_raw_hash_and_model_kickoff_conflict(self):
        s = source()
        s["_same_response_source_sha256"] = "b"*64
        with self.assertRaisesRegex(ValueError, "ONE_GET_RAW_SOURCE_HASH_MISSING"):
            gather(s)
        p = forecasts()
        p[0]["kickoff_utc"] = "2026-11-20T12:30:00Z"
        with self.assertRaisesRegex(ValueError, "SOURCE_VS_MODEL_KICKOFF_CONFLICT"):
            gather(p=p)

    def test_reject_no_future_fixtures_and_too_little_history(self):
        s = source()
        s["matches"] = [row for row in s["matches"] if row["status"] == "FINISHED"]
        with self.assertRaisesRegex(ValueError, "NO_FRESH_UNSELECTED_SOURCE_FIXTURES"):
            gather(s)
        s = source()
        s["matches"] = s["matches"][:7] + s["matches"][-2:]
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_PAST_KICKOFF_RECORDS"):
            gather(s)

    def test_reject_after_source_observation_non_earlier_results(self):
        s = source()
        s["matches"][0]["date"] = "2026-11-15"
        s["matches"][0]["kickoff_utc"] = "2026-11-17T12:00:00Z"
        with self.assertRaisesRegex(ValueError, "HISTORICAL_KICKOFF_NOT_PRIOR_TO_RECEIPT"):
            gather(s)


if __name__ == "__main__":
    unittest.main()
