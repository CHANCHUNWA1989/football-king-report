"""Fixed-24h retrospective scoring tests: never confuse with a true forward trial."""
from datetime import datetime, timedelta, timezone
import copy
import unittest
from unittest.mock import patch

from ops import identity_ab_walkforward as walk
from ops import identity_ab_compare as ab
from ops.tests.test_identity_ab_openliga_probe import NOW, source, encoded
from ops.identity_ab_openliga_probe import normalize


def cases():
    rows, _ = normalize(encoded(source()), year=2026,
                        observed_utc=NOW.isoformat())
    return rows


class RetrospectiveWalkforwardTests(unittest.TestCase):
    def test_reports_all_cases_and_score_intersection_only(self):
        rows=cases()
        original=copy.deepcopy(rows)
        result=walk.assess(rows, observed_utc=NOW.isoformat())
        self.assertEqual(rows,original)
        counts=result["counts"]
        self.assertEqual(counts["observed_source_ft"],36)
        self.assertGreater(counts["paired_predictions_scored"],0)
        self.assertLessEqual(counts["paired_predictions_scored"],36)
        self.assertEqual(
            counts["paired_predictions_scored"]+counts["legacy_only"]
            +counts["candidate_only"]+counts["neither_predicted"],36)
        for metric in ("legacy_mean_log_loss","candidate_mean_log_loss",
                       "legacy_mean_brier","candidate_mean_brier",
                       "legacy_top_direction_accuracy_on_paired",
                       "candidate_top_direction_accuracy_on_paired"):
            self.assertIsNotNone(result["summary"][metric])
        self.assertTrue(result["no_outcome_leakage_in_model_inputs_by_construction"])
        self.assertFalse(result["historical_source_available_at_cutoff_authenticated"])
        self.assertFalse(result["source_results_independently_verified"])
        self.assertFalse(result["real_pre_match_prediction_archive_exists"])
        self.assertFalse(result["accuracy_uplift_proven"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_all_candidate_y_removed_before_both_engines(self):
        rows=cases()
        original=ab.compare
        seen=0
        def strict(input_rows, *, league, as_of_utc, **kwargs):
            nonlocal seen
            seen+=1
            now=datetime.fromisoformat(as_of_utc)
            today=now.astimezone(walk.HK).date()
            scheduled=[row for row in input_rows if row["status"]=="SCHEDULED"]
            self.assertEqual(len(scheduled),1)
            self.assertIsNone(scheduled[0]["score_ft"])
            for item in input_rows:
                if item["status"]=="FINISHED":
                    self.assertLess(datetime.fromisoformat(
                        item["date"]).date(),today)
                    self.assertIsNotNone(item["score_ft"])
            return original(input_rows,league=league,as_of_utc=as_of_utc,**kwargs)
        with patch.object(walk,"compare",side_effect=strict):
            walk.assess(rows,observed_utc=NOW.isoformat())
        self.assertEqual(seen,36)

    def test_reordered_source_array_same_retrospective_result(self):
        rows=cases()
        forward=walk.assess(rows,observed_utc=NOW.isoformat())
        reverse=walk.assess(list(reversed(rows)),observed_utc=NOW.isoformat())
        self.assertEqual(forward,reverse)

    def test_completed_today_or_after_observed_rejected(self):
        rows=cases()
        invalid=copy.deepcopy(rows[0])
        invalid["date"]="2026-11-08"
        invalid["kickoff_utc"]="2026-11-08T10:00:00+00:00"
        with self.assertRaisesRegex(ValueError,"WALKFORWARD_TIME_OR_RESULT_LEAKAGE"):
            walk.assess(rows+[invalid], observed_utc=NOW.isoformat())

    def test_scheduled_future_result_rejected(self):
        rows=cases()
        for future in ({"status":"SCHEDULED","score_ft":[2,0]},
                       {"status":"SCHEDULED","score_ft":(2,0)}):
            new=copy.deepcopy(rows)
            new.append({**rows[0],**future,"event_id":"fake-fixture"})
            with self.assertRaisesRegex(ValueError,"FUTURE_RESULT_LEAKAGE"):
                walk.assess(new, observed_utc=NOW.isoformat())

    def test_double_counted_historical_event_id_rejected(self):
        rows=cases()
        with self.assertRaisesRegex(ValueError,"DUPLICATE_WALKFORWARD_RESULT"):
            walk.assess(rows+[dict(rows[0])],observed_utc=NOW.isoformat())


if __name__=="__main__":
    unittest.main()
