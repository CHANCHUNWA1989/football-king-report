"""V17 fully synthetic prequential Elo replay: no real KPL data imported."""
import copy
import hashlib
import unittest
from datetime import datetime, timedelta, timezone

from research.kpl_v17_elo_replay import replay_elo_shadow

BASE=datetime(2026,1,1,tzinfo=timezone.utc)


def iso(t):
    return t.isoformat().replace("+00:00","Z")


def rows(n=4, *, same_patch=True, winner="team-A"):
    arr=[]
    for series in range(n):
        for game in range(1,5):
            started=BASE+timedelta(days=3*series,hours=game*2)
            arr.append({
                "series_id":f"synthetic-bo-{series}",
                "game_number":game,"team_a":"team-A","team_b":"team-B",
                "winner_team_id":winner,
                "patch_id":"patch-P1" if same_patch else f"patch-{series}",
                "forecast_at":iso(started-timedelta(minutes=10)),
                "game_start_at":iso(started),
                "result_observed_at":iso(started+timedelta(minutes=30)),
                "source_id":f"synthetic-source-{series}-{game}",
                "source_class":"SYNTHETIC",
                "source_record_sha256":hashlib.sha256(
                    f"synthetic:{series}:{game}".encode()).hexdigest()
            })
    return arr


def run(data=None, **kwargs):
    settings = dict(model_frozen_at=iso(BASE-timedelta(days=1)),
                    universe_registered_at=iso(BASE-timedelta(days=1)),
                    registered_series_ids=[f"synthetic-bo-{x}" for x in range(4)],
                    train_fraction=0.5,min_test_series=2,min_test_maps=8,
                    repetitions=200)
    settings.update(kwargs)
    return replay_elo_shadow(rows() if data is None else data, **settings)


class KplV17Tests(unittest.TestCase):
    def test_success_synthetic_still_hold(self):
        r=run()
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["real_kpl_accuracy_verified"])
        self.assertFalse(r["provider_data_rights_independently_verified"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["live_execution_allowed"])
        self.assertEqual(r["test_series"],2)
        self.assertEqual(r["test_maps"],8)

    def test_first_game_neutral_50_before_any_result(self):
        r=run()
        first=r["test_forecasts"][0]
        self.assertEqual(first["game_number"],1)
        self.assertGreater(first["probability_a"],0.5)
        self.assertFalse(first["is_calibrated_probability"])

    def test_elo_baseline_brier_not_claiming_skill(self):
        r=run()
        self.assertGreater(r["paired_brier_gain_vs_uniform_50"],0)
        self.assertEqual(r["uniform_50_baseline"]["brier"],0.25)
        self.assertEqual(r["source_class"],"SYNTHETIC")
        self.assertFalse(r["model_calibrated_on_real_kpl"])

    def test_test_set_forecasts_not_backfilled(self):
        base=run()
        flipped=rows()
        for rec in flipped:
            if rec["series_id"]=="synthetic-bo-3":
                rec["winner_team_id"]="team-B"
        other=run(flipped)
        before=[r["probability_a"] for r in base["test_forecasts"]
                if r["series_id"]=="synthetic-bo-3"]
        after=[r["probability_a"] for r in other["test_forecasts"]
               if r["series_id"]=="synthetic-bo-3"]
        self.assertEqual(before[0],after[0])
        self.assertNotEqual(before[-1],after[-1])

    def test_not_yet_observed_previous_map_cannot_be_used(self):
        history=rows()
        history[8]["result_observed_at"]=iso(
            BASE+timedelta(days=6,hours=4,minutes=5))
        r=run(history)
        g2=[x for x in r["test_forecasts"]
            if x["series_id"]=="synthetic-bo-2" and x["game_number"]==2][0]
        self.assertEqual(g2["probability_a"],
                         [x for x in r["test_forecasts"]
                          if x["series_id"]=="synthetic-bo-2" and x["game_number"]==1][0]["probability_a"])

    def test_new_patch_resets_team_elo(self):
        r=run(rows(same_patch=False))
        first_of_test=[x for x in r["test_forecasts"] if x["game_number"]==1]
        self.assertEqual([x["probability_a"] for x in first_of_test],[0.5,0.5])

    def test_duplicate_game_rejected(self):
        history=rows()
        history.append(copy.deepcopy(history[0]))
        with self.assertRaisesRegex(ValueError,"duplicate series game"):
            run(history)

    def test_incomplete_bo7_rejected(self):
        history=rows()
        history=[r for r in history if not (r["series_id"]=="synthetic-bo-1"
                                            and r["game_number"]==4)]
        with self.assertRaisesRegex(ValueError,"incomplete or oversized BO7"):
            run(history)

    def test_gapped_game_rejected(self):
        history=rows()
        history[4]["game_number"]=3
        with self.assertRaises(ValueError):
            run(history)

    def test_more_than_four_wins_cannot_continue(self):
        history=rows()
        additional=copy.deepcopy(history[3])
        additional["game_number"]=5
        additional["forecast_at"]=iso(BASE+timedelta(hours=9,minutes=50))
        additional["game_start_at"]=iso(BASE+timedelta(hours=10))
        additional["result_observed_at"]=iso(BASE+timedelta(hours=10,minutes=30))
        history.append(additional)
        with self.assertRaisesRegex(ValueError,"already decided"):
            run(history)

    def test_forecast_after_game_started_rejected(self):
        history=rows()
        history[0]["forecast_at"]=history[0]["game_start_at"]
        with self.assertRaisesRegex(ValueError,"forecast or outcome time leakage"):
            run(history)

    def test_outcome_before_game_started_rejected(self):
        history=rows()
        history[0]["result_observed_at"]=history[0]["forecast_at"]
        with self.assertRaisesRegex(ValueError,"forecast or outcome time leakage"):
            run(history)

    def test_training_result_not_known_before_holdout_rejected(self):
        history=rows()
        history[7]["result_observed_at"]=iso(BASE+timedelta(days=7))
        with self.assertRaisesRegex(ValueError,"test split overlaps"):
            run(history)

    def test_model_policy_frozen_after_start_rejected(self):
        with self.assertRaisesRegex(ValueError,"model policy frozen"):
            replay_elo_shadow(
                rows(),model_frozen_at=iso(BASE+timedelta(days=1)),
                universe_registered_at=iso(BASE-timedelta(days=1)),
                registered_series_ids=[f"synthetic-bo-{x}" for x in range(4)],
                min_test_series=2,min_test_maps=8,repetitions=200)

    def test_insufficient_test_series_stays_hold(self):
        r=run(min_test_series=3)
        self.assertIn("INSUFFICIENT_INDEPENDENT_HOLDOUT_SERIES_OR_MAPS",r["reasons"])
        self.assertEqual(r["status"],"HOLD")

    def test_synthetic_cannot_mix_other_grade(self):
        history=rows()
        history[-1]["source_class"]="UNVERIFIED_PUBLIC"
        with self.assertRaisesRegex(ValueError,"cannot mix synthetic"):
            run(history)

    def test_forged_digest_shape_fails(self):
        history=rows()
        history[0]["source_record_sha256"]="not-sha256"
        with self.assertRaisesRegex(ValueError,"invalid source digest"):
            run(history)

    def test_invalid_source_class_fails(self):
        history=rows()
        history[0]["source_class"]="OFFICIAL_TRUSTED"
        with self.assertRaisesRegex(ValueError,"invalid source class"):
            run(history)

    def test_history_input_order_does_not_look_ahead(self):
        baseline=run()
        reversed_order=run(list(reversed(rows())))
        self.assertEqual(
            [x["probability_a"] for x in baseline["test_forecasts"]],
            [x["probability_a"] for x in reversed_order["test_forecasts"]])

    def test_same_result_all_kpl_matches_does_not_prove_skilled_model(self):
        result=run()
        self.assertGreater(result["elo_model"]["direction_coverage"],0)
        self.assertEqual(result["status"],"HOLD")
        self.assertIn("BENCHMARK_ELO_NOT_REAL_KPL_CALIBRATION",result["reasons"])

    def test_invalid_hyperparameter_refused(self):
        with self.assertRaisesRegex(ValueError,"invalid frozen benchmark policy"):
            run(elo_k=1000)

    def test_undisclosed_excluded_series_rejected(self):
        history = [x for x in rows() if x["series_id"] != "synthetic-bo-3"]
        with self.assertRaisesRegex(ValueError, "registered series universe coverage"):
            run(history)

    def test_universe_registered_after_first_prediction_rejected(self):
        with self.assertRaisesRegex(ValueError, "registered after first forecast"):
            run(universe_registered_at=iso(BASE+timedelta(days=1)))

    def test_duplicate_source_snapshot_digest_rejected(self):
        history=rows()
        history[1]["source_record_sha256"]=history[0]["source_record_sha256"]
        with self.assertRaisesRegex(ValueError, "duplicate source digest"):
            run(history)

    def test_unhashable_untrusted_source_class_rejected(self):
        history=rows()
        history[1]["source_class"]=[]
        with self.assertRaisesRegex(ValueError, "invalid source class"):
            run(history)

    def test_no_network_or_live_execution_path(self):
        r=run()
        self.assertIsNone(r.get("wager_amount"))
        self.assertIsNone(r.get("executable_quote"))
        self.assertFalse(r["positive_ev_verified"])


if __name__=="__main__":
    unittest.main()
