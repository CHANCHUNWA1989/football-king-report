"""Synthetic-only red-card paired exposure research tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from red_card_paired_exposure import summarize


def bucket(cards, minutes, xg, shots=(3, 3)):
    return {"dismissals": list(cards), "elapsed_minutes": minutes,
            "xg": list(xg), "shots": list(shots)}


def fixture(mid=1, away=False, post=30):
    return {"match_id":mid,"regulation_cards":1,"buckets":[
        bucket((0,0),60,(1.2,.6) if not away else (.6,1.2)),
        bucket((0,1) if away else (1,0),post,(.9,.2) if away else (.2,.9))]}


class PairedExposureTests(unittest.TestCase):
    def test_home_away_orientation_and_exposure_weighting(self):
        r=summarize([fixture(),fixture(2,True)])
        self.assertEqual(r["accepted_matches"],2)
        self.assertAlmostEqual(r["dismissed_team"]["pre_xg_per_90"],1.8)
        self.assertAlmostEqual(r["dismissed_team"]["post_xg_per_90"],.6)
        self.assertAlmostEqual(r["opponent"]["pre_xg_per_90"],.9)
        self.assertAlmostEqual(r["opponent"]["post_xg_per_90"],2.7)
        self.assertFalse(r["causal_effect_estimated"])
        self.assertEqual(r["verified_forward_sample_credit"],0)

    def test_exposure_weighting_not_average_of_individual_rates(self):
        a,b=fixture(),fixture(2,post=20)
        b["buckets"][0]["elapsed_minutes"]=70
        self.assertAlmostEqual(summarize([a,b])["dismissed_team"]["post_xg_per_90"],.72)

    def test_duplicate_group_never_selected(self):
        self.assertEqual(summarize([fixture(),fixture()])["accepted_matches"],0)
        self.assertEqual(summarize([fixture(),fixture()])["rejected"]["DUPLICATE_MATCH"],2)

    def test_short_or_multiple_dismissals_do_not_enter_single_card_cohort(self):
        a=fixture(post=10)
        a["buckets"][0]["elapsed_minutes"]=80
        b=fixture(2);b["regulation_cards"]=2
        r=summarize([a,b])
        self.assertEqual(r["accepted_matches"],0)
        self.assertEqual(r["rejected"]["INSUFFICIENT_EXPOSURE"],1)
        self.assertEqual(r["rejected"]["NOT_SINGLE_DISMISSAL"],1)
        self.assertIsNone(r["dismissed_team"])

    def test_invalid_xg_and_exposure_fail_closed(self):
        for value in (float("nan"),-1,True,10):
            a=fixture();a["buckets"][1]["xg"][0]=value
            self.assertEqual(summarize([a])["accepted_matches"],0)
        a=fixture();a["buckets"][1]["elapsed_minutes"]=1000
        self.assertEqual(summarize([a])["accepted_matches"],0)

    def test_paired_bootstrap_identical_cases_and_order_invariance(self):
        rows=[fixture(i, i%2==0) for i in range(1,31)]
        a=summarize(rows)["uncertainty"]
        self.assertEqual(a,summarize(list(reversed(rows)))["uncertainty"])
        self.assertEqual(a["status"],"DESCRIPTIVE_INTERVAL_ONLY")
        self.assertEqual(a["replicates"],1000)
        bounds=a["rate_difference_intervals"]["dismissed_team"]
        self.assertAlmostEqual(bounds["lower"],-1.2)
        self.assertAlmostEqual(bounds["upper"],-1.2)
        self.assertFalse(a["inferentially_validated"])

    def test_small_sample_suppresses_interval(self):
        r=summarize([fixture(1),fixture(2)])
        self.assertEqual(r["uncertainty"]["status"],"INSUFFICIENT_SAMPLE")
        self.assertIsNone(r["uncertainty"]["rate_difference_intervals"])

    def test_exposure_threshold_sensitivity_and_leave_one_out(self):
        rows=[fixture(1),fixture(2,post=20)]
        rows[1]["buckets"][0]["elapsed_minutes"]=70
        r=summarize(rows)
        by={s["minimum_minutes_each_state"]:s for s in r["exposure_sensitivity"]}
        self.assertEqual(by[15]["matches"],2)
        self.assertEqual(by[20]["matches"],2)
        self.assertEqual(by[30]["matches"],1)
        self.assertAlmostEqual(by[30]["dismissed_team"]["rate_difference"],-1.2)
        bounds=r["influence"]["dismissed_team"]["leave_one_out_rate_difference_range"]
        self.assertAlmostEqual(bounds["lower"],-1.2)
        self.assertAlmostEqual(bounds["upper"],.9-90*1.2/70)
        self.assertFalse(r["model_calibrated"])

    def test_equal_fixture_and_pooled_effects_distinct(self):
        a,b=fixture(),fixture(2,post=20)
        b["buckets"][0]["elapsed_minutes"]=70
        r=summarize([a,b])
        self.assertNotAlmostEqual(r["influence"]["dismissed_team"]["equal_fixture_mean_difference"],
                                  r["dismissed_team"]["rate_difference"])

    def test_declared_score_state_is_oriented_to_dismissed_team(self):
        a,b,c=fixture(1),fixture(2,True),fixture(3)
        a["score_immediately_before_dismissal"]=[2,1]
        b["score_immediately_before_dismissal"]=[2,1]
        c["score_immediately_before_dismissal"]=[0,0]
        r=summarize([a,b,c])["tactical_strata"]
        self.assertEqual(r["score_context_counts"],{"LEADING":1,"DRAWING":1,"TRAILING":1,"UNKNOWN":0})
        self.assertFalse(r["score_claims_authenticated"])
        self.assertFalse(r["confounding_adjusted"])

    def test_missing_and_invalid_score_context_is_not_inferred(self):
        a,b,c,d=fixture(1),fixture(2),fixture(3),fixture(4)
        b["score_immediately_before_dismissal"]=[True,0]
        c["score_immediately_before_dismissal"]=[-1,0]
        d["score_immediately_before_dismissal"]="1-0"
        r=summarize([a,b,c,d])
        self.assertEqual(r["accepted_matches"],4)
        s=r["tactical_strata"]
        self.assertEqual(s["score_context_counts"]["UNKNOWN"],4)
        self.assertEqual(s["missing_score_context"],1)
        self.assertEqual(s["invalid_score_context"],3)

    def test_fixed_elapsed_bands_and_sparse_strata(self):
        a,b,c=fixture(1),fixture(2),fixture(3)
        for row,pre in ((a,30),(b,45),(c,60)):
            row["buckets"][0]["elapsed_minutes"]=pre
            row["buckets"][1]["elapsed_minutes"]=90-pre
            row["score_immediately_before_dismissal"]=[1,0]
        r=summarize([a,b,c])["tactical_strata"]
        self.assertEqual(r["elapsed_band_counts"],{"LT_30":0,"30_TO_LT_60":2,"GE_60":1})
        self.assertEqual(sum(g["matches"] for g in r["groups"]),3)
        self.assertTrue(all(g["rates"] is None for g in r["groups"]))

    def test_sufficient_group_reports_descriptives_not_calibration(self):
        rows=[fixture(i) for i in range(1,11)]
        for row in rows:
            row["score_immediately_before_dismissal"]=[0,0]
        r=summarize(rows)
        g=r["tactical_strata"]["groups"][0]
        self.assertEqual(g["matches"],10)
        self.assertAlmostEqual(g["rates"]["dismissed_team"]["rate_difference"],-1.2)
        self.assertFalse(r["model_calibrated"])
        self.assertEqual(r["verified_forward_sample_credit"],0)

    def _strength(self, row, home=1600, away=1400):
        row.update(home_id=11,away_id=22,kickoff_utc="2026-11-25T19:00:00Z")
        row["prematch_strength"]={
            "match_id":row["match_id"],"home_id":11,"away_id":22,
            "model_id":"elo-v1","scale":"ELO_POINTS",
            "home_rating":home,"away_rating":away,
            "training_cutoff_utc":"2026-11-24T00:00:00Z",
            "recorded_utc":"2026-11-25T18:00:00Z"}
        return row

    def test_prematch_strength_orientation_and_fixed_bands(self):
        rows=[self._strength(fixture(1)),self._strength(fixture(2,True)),
              self._strength(fixture(3),1500,1450)]
        r=summarize(rows)["strength_strata"]
        self.assertEqual(r["counts"],{"STRONGER":1,"SIMILAR":1,"WEAKER":1,"UNKNOWN":0})
        self.assertFalse(r["ratings_authenticated"])
        self.assertFalse(r["confounding_adjusted"])

    def test_late_mismatched_or_invalid_rating_claims_stay_unknown(self):
        rows=[self._strength(fixture(i)) for i in range(1,7)]
        rows[0]["prematch_strength"]["recorded_utc"]="2026-11-25T19:00:00Z"
        rows[1]["prematch_strength"]["training_cutoff_utc"]="2026-11-26T00:00:00Z"
        rows[2]["prematch_strength"]["home_id"]=22
        rows[3]["prematch_strength"]["away_rating"]=True
        rows[4]["prematch_strength"]["match_id"]=99
        rows[5]["prematch_strength"]["recorded_utc"]="2026-11-25T18:00:00"
        r=summarize(rows)
        self.assertEqual(r["accepted_matches"],6)
        self.assertEqual(r["strength_strata"]["invalid_context"],6)
        self.assertEqual(r["strength_strata"]["counts"]["UNKNOWN"],6)

    def test_missing_strength_preserves_legacy_research_without_claim(self):
        r=summarize([fixture()])
        self.assertEqual(r["strength_strata"]["missing_context"],1)
        self.assertEqual(r["strength_strata"]["counts"]["UNKNOWN"],1)
        self.assertIsNone(r["strength_strata"]["groups"][0]["rates"])

    def test_mixed_rating_versions_never_pool_rate_estimates(self):
        rows=[self._strength(fixture(i)) for i in range(1,11)]
        rows[-1]["prematch_strength"]["model_id"]="elo-v2"
        r=summarize(rows)["strength_strata"]
        self.assertEqual(r["groups"][0]["status"],"MIXED_RATING_MODELS")
        self.assertIsNone(r["groups"][0]["rates"])

    def test_consistent_rating_group_reports_only_descriptive_rates(self):
        rows=[self._strength(fixture(i)) for i in range(1,11)]
        r=summarize(rows)
        g=r["strength_strata"]["groups"][0]
        self.assertEqual(g["status"],"DESCRIPTIVE_ONLY")
        self.assertAlmostEqual(g["rates"]["dismissed_team"]["rate_difference"],-1.2)
        self.assertFalse(r["model_calibrated"])
        self.assertEqual(r["verified_forward_sample_credit"],0)

    def _player(self,row,position="GOALKEEPER",away=False):
        row.update(home_id=11,away_id=22)
        row["dismissal_player_context"]={
            "match_id":row["match_id"],"team_id":22 if away else 11,
            "player_id":123,"position_at_dismissal":position,
            "card_event_id":"event-123","position_source":"declared-event-roster",
            "on_pitch_immediately_before":True}
        return row

    def test_player_position_oriented_to_dismissed_team(self):
        rows=[self._player(fixture(1)),self._player(fixture(2,True),"CENTRE_BACK",True),
              self._player(fixture(3),"FORWARD")]
        s=summarize(rows)["player_position_strata"]
        self.assertEqual(s["counts"]["GOALKEEPER"],1)
        self.assertEqual(s["counts"]["CENTRE_BACK"],1)
        self.assertEqual(s["counts"]["FORWARD"],1)
        self.assertFalse(s["player_identity_authenticated"])
        self.assertFalse(s["replacement_goalkeeper_observed"])

    def test_invalid_player_claims_do_not_create_known_positions(self):
        rows=[self._player(fixture(i)) for i in range(1,7)]
        rows[0]["dismissal_player_context"]["team_id"]=22
        rows[1]["dismissal_player_context"]["player_id"]=True
        rows[2]["dismissal_player_context"]["match_id"]=99
        rows[3]["dismissal_player_context"]["on_pitch_immediately_before"]=False
        rows[4]["dismissal_player_context"]["position_at_dismissal"]="STAR"
        rows[5]["dismissal_player_context"]["card_event_id"]=""
        r=summarize(rows)
        self.assertEqual(r["accepted_matches"],6)
        self.assertEqual(r["player_position_strata"]["invalid_context"],6)
        self.assertEqual(r["player_position_strata"]["counts"]["UNKNOWN"],6)

    def test_missing_player_context_is_not_inferred(self):
        r=summarize([fixture()])
        s=r["player_position_strata"]
        self.assertEqual(s["missing_context"],1)
        self.assertEqual(s["counts"]["UNKNOWN"],1)
        self.assertIsNone(s["groups"][0]["rates"])

    def test_position_rates_require_ten_matches(self):
        rows=[self._player(fixture(i),"MIDFIELDER") for i in range(1,11)]
        self.assertIsNone(summarize(rows[:9])["player_position_strata"]["groups"][0]["rates"])
        r=summarize(rows)
        g=r["player_position_strata"]["groups"][0]
        self.assertAlmostEqual(g["rates"]["dismissed_team"]["rate_difference"],-1.2)
        self.assertFalse(r["player_position_strata"]["individual_importance_estimated"])
        self.assertFalse(r["model_calibrated"])

    def test_joint_strata_never_impute_missing_dimensions(self):
        rows=[self._player(self._strength(fixture(i)),"CENTRE_BACK") for i in range(1,11)]
        for row in rows:
            row["score_immediately_before_dismissal"]=[1,0]
        r=summarize(rows+[fixture(99)])["joint_context_strata"]
        self.assertEqual(r["complete_context_matches"],10)
        self.assertEqual(r["incomplete_context_matches"],1)
        self.assertEqual(len(r["groups"]),1)
        g=r["groups"][0]
        self.assertEqual((g["strength_band"],g["score_state"],g["elapsed_band"],g["position"]),
                         ("STRONGER","LEADING","GE_60","CENTRE_BACK"))
        self.assertAlmostEqual(g["rates"]["opponent"]["rate_difference"],1.8)
        self.assertFalse(r["confounding_adjusted"])

    def test_joint_strata_blocks_mixed_rating_versions(self):
        rows=[self._player(self._strength(fixture(i)),"CENTRE_BACK") for i in range(1,11)]
        for row in rows:
            row["score_immediately_before_dismissal"]=[0,0]
        rows[-1]["prematch_strength"]["model_id"]="elo-v2"
        g=summarize(rows)["joint_context_strata"]["groups"][0]
        self.assertEqual(g["status"],"MIXED_RATING_MODELS")
        self.assertIsNone(g["rates"])

    def test_sample_threshold_never_certifies(self):
        r=summarize([fixture(i) for i in range(1,31)])
        self.assertFalse(r["small_sample"])
        self.assertFalse(r["model_calibrated"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["status"],"HOLD")


if __name__=="__main__":
    unittest.main()
