"""Synthetic normalization tests for real-bounded, single-GET Bundesliga A/B probe."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest

from ops import identity_ab_openliga_probe as probe
from ops.identity_ab_compare import _instant

NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)


def game(index, *, finished=True, kickoff=None):
    if kickoff is None:
        kickoff = ((NOW - timedelta(days=index+1) if finished
                    else NOW + timedelta(days=1))
                   .replace(hour=12)).isoformat().replace("+00:00","Z")
    return {
        "matchID": 100000 + index,
        "leagueShortcut": "bl1", "leagueSeason": 2026, "leagueId": 4331,
        "team1": {"teamId": 5, "teamName": "Bayern Munich"},
        "team2": {"teamId": 8, "teamName": "Borussia Dortmund"},
        "matchDateTimeUTC": kickoff,
        "matchIsFinished": finished,
        "matchResults": (
            [{"resultTypeKind":"After90Minutes",
              "pointsTeam1":4 if index % 2 == 0 else 1,
              "pointsTeam2":0 if index % 2 == 0 else 2}]
            if finished else []),
    }


def source():
    return [game(i) for i in range(36)] + [game(75, finished=False)]


def encoded(rows):
    return json.dumps(rows,sort_keys=True).encode("utf-8")


class OpenligaForwardAbTests(unittest.TestCase):
    def test_pre_match_snapshot_and_one_source_ab(self):
        raw=encoded(source())
        rows, counts=probe.normalize(raw,year=2026,observed_utc=NOW.isoformat())
        self.assertEqual(len(rows),37)
        self.assertEqual(counts["eligible_past_90min_rows"],36)
        self.assertEqual(counts["eligible_upcoming_no_score_rows"],1)
        self.assertEqual(sum(row["status"]=="SCHEDULED" for row in rows),1)
        result=probe.probe(year=2026, observed_utc=NOW.isoformat(),raw=raw,
                           source_commit="b"*40)
        self.assertEqual(result["raw_source_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["ab"]["counts"]["paired"],1)
        self.assertFalse(result["prediction_accuracy_improved_proven"])
        self.assertFalse(result["ab"]["model_accuracy_improved_proven"])
        self.assertFalse(result["provider_capture_authenticated"])
        self.assertFalse(result["90min_score_source_independently_verified"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_same_day_finished_observation_never_enters_training(self):
        rows=source()
        rows.append(game(99,kickoff="2026-11-08T10:00:00Z"))
        normalized,counts=probe.normalize(encoded(rows),year=2026,
                                          observed_utc=NOW.isoformat())
        self.assertEqual(counts["same_day_result_excluded"],1)
        self.assertEqual(len(normalized),37)

    def test_in_progress_score_never_masquerades_as_future_prediction(self):
        rows=source()
        rows[-1]["matchResults"]=[{"resultTypeKind":"HalfTime",
                                   "pointsTeam1":1,"pointsTeam2":1}]
        normalized,counts=probe.normalize(encoded(rows),year=2026,
                                          observed_utc=NOW.isoformat())
        self.assertEqual(counts["eligible_upcoming_no_score_rows"],0)
        self.assertEqual(counts["out_of_window_or_incomplete_excluded"],1)
        self.assertEqual(len(normalized),36)

    def test_duplicate_native_event_id_fail_closed(self):
        rows=source()
        rows.append(copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(probe.ForwardProbeError,
                                    "DUPLICATE_NATIVE_FIXTURE_ID"):
            probe.normalize(encoded(rows),year=2026,observed_utc=NOW.isoformat())

    def test_provider_id_to_conflicting_name_fail_closed(self):
        rows=source()
        # Change native team 5 to another club WITHOUT also making it the
        # same as the away team in that single fixture.
        rows[1]["team1"]["teamName"]="RB Leipzig"
        with self.assertRaisesRegex(probe.ForwardProbeError,
                                    "CONFLICTING_PROVIDER_TEAM_IDENTITY"):
            probe.normalize(encoded(rows),year=2026,observed_utc=NOW.isoformat())

    def test_provider_name_to_conflicting_id_fail_closed(self):
        rows=source()
        rows[1]["team1"]["teamId"]=99
        with self.assertRaisesRegex(probe.ForwardProbeError,
                                    "CONFLICTING_PROVIDER_TEAM_IDENTITY"):
            probe.normalize(encoded(rows),year=2026,observed_utc=NOW.isoformat())

    def test_away_and_home_native_id_cannot_be_same(self):
        rows=source()
        rows[0]["team2"]["teamId"]=5
        with self.assertRaisesRegex(probe.ForwardProbeError,
                                    "INVALID_PROVIDER_FIXTURE_IDENTITY"):
            probe.normalize(encoded(rows),year=2026,observed_utc=NOW.isoformat())

    def test_non_unique_league_id_fail_closed(self):
        rows=source()
        rows[10]["leagueId"]=999
        with self.assertRaisesRegex(probe.ForwardProbeError,
                                    "INVALID_SINGLE_SOURCE_LEAGUE_ID"):
            probe.normalize(encoded(rows),year=2026,observed_utc=NOW.isoformat())

    def test_wrong_season_and_nonfinite_json_rejected(self):
        rows=source()
        for row in rows:
            row["leagueSeason"]=2025
        with self.assertRaisesRegex(probe.ForwardProbeError,
                                    "INVALID_SINGLE_SOURCE_LEAGUE_ID"):
            probe.normalize(encoded(rows),year=2026,observed_utc=NOW.isoformat())
        with self.assertRaisesRegex(probe.ForwardProbeError,
                                    "INVALID_PROVIDER_BODY"):
            probe.normalize(b'[NaN]',year=2026,observed_utc=NOW.isoformat())

    def test_future_result_score_must_never_be_used_as_y(self):
        rows=source()
        rows[-1]["matchIsFinished"]=True
        rows[-1]["matchResults"]=[
            {"resultTypeKind":"After90Minutes","pointsTeam1":9,"pointsTeam2":0}
        ]
        normalized,counts=probe.normalize(encoded(rows),year=2026,
                                          observed_utc=NOW.isoformat())
        self.assertEqual(counts["same_day_result_excluded"],1)
        self.assertEqual(sum(row["status"]=="SCHEDULED" for row in normalized),0)

    def test_source_order_does_not_change_normalized_rows_or_results(self):
        rows=source()
        a=probe.probe(year=2026,observed_utc=NOW.isoformat(),raw=encoded(rows))
        # Full provider body SHA changes, but deterministic normalized
        # fixture inputs and A/B output must not.
        b=probe.probe(year=2026,observed_utc=NOW.isoformat(),
                      raw=encoded(list(reversed(rows))))
        self.assertNotEqual(a["raw_source_sha256"],b["raw_source_sha256"])
        self.assertEqual(a["ab"],b["ab"])
        self.assertEqual(a["source_coverage"],b["source_coverage"])


if __name__=="__main__":
    unittest.main()
