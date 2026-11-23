"""Synthetic only: do not treat fixtures as verified football or market data."""
import unittest
from datetime import datetime, timezone
from ops.shadow_eligibility_diagnostics import summarize

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)

def fixture(kickoff='2026-11-23T20:00:00Z'):
    return {'status':'SCHEDULED', 'date':'2026-11-24',
            'home':'Home', 'away':'Away','kickoff_utc':kickoff, 'score_ft':None}

def score():
    return {'status':'FINISHED','date':'2026-11-20','home':'Home','away':'Away','score_ft':[1,0]}

class ShadowSourceCoverageTests(unittest.TestCase):
    def test_zero_source_scheduled_rows_diagnosed(self):
        r=summarize([score()], [], NOW)
        self.assertEqual(r['reason'],'NO_UNPLAYED_SCHEDULED_ROWS')
        self.assertEqual(r['prior_finished_score_rows'],1)
        self.assertEqual(r['production_recommendations'],'DISABLED')

    def test_missing_precise_schedule_not_promoted(self):
        r=summarize([score(),fixture(None)],[],NOW)
        self.assertEqual(r['scheduled_missing_precise_utc'],1)
        self.assertEqual(r['reason'],'NO_ELIGIBLE_PRECISE_KICKOFF_ROWS')
        self.assertFalse(r['source_utc_authenticated'])
        self.assertEqual(r['status'],'HOLD')

    def test_aware_kickoff_and_twelve_prior_games_still_hold(self):
        r=summarize([score() for _ in range(12)]+[fixture()],[],NOW)
        self.assertEqual(r['scheduled_valid_precise_utc'],1)
        self.assertEqual(r['reason'],'FEWER_THAN_30_PRIOR_FINISHED_SCORE_ROWS')
        self.assertEqual(r['independently_validated_result_rows'],0)

    def test_observed_history_does_not_fake_model_output(self):
        r=summarize([score() for _ in range(40)]+[fixture()],[],NOW)
        self.assertEqual(r['reason'],'ZERO_FORECAST_WITH_VALID_SCHEDULE_REVIEW_TRAINING_OR_IDENTITY')
        self.assertEqual(r['predictions_emitted'],0)
        self.assertFalse(r['verified_positive_ev'])

    def test_report_available_prediction_remains_uncalibrated(self):
        forecast={'event_id':'fake-study'}
        p=[forecast]
        r=summarize([score() for _ in range(40)]+[fixture()],p,NOW)
        self.assertEqual(r['reason'],'UNCALIBRATED_SHADOW_PREDICTIONS_ONLY')
        self.assertEqual(r['status'],'SHADOW_ONLY')
        self.assertIs(p[0],forecast)
        self.assertEqual(r['production_recommendations'],'DISABLED')

    def test_wrong_local_date_is_rejected(self):
        row=fixture();row['date']='2026-11-23'
        r=summarize([row],[],NOW)
        self.assertEqual(r['scheduled_invalid_or_outside_window'],1)
        self.assertEqual(r['scheduled_valid_precise_utc'],0)

    def test_bad_offset_and_nan_date_never_count_as_precise(self):
        r=summarize([fixture('2026-11-24T04:00:00'),fixture('not-a-time')],[],NOW)
        self.assertEqual(r['scheduled_missing_precise_utc'],2)
        self.assertEqual(r['scheduled_valid_precise_utc'],0)

    def test_future_past_kickoff_not_counted(self):
        r=summarize([fixture('2026-11-23T11:00:00Z')],[],NOW)
        self.assertEqual(r['scheduled_invalid_or_outside_window'],1)

    def test_no_betting_from_known_prediction(self):
        r=summarize([fixture()], [{'p_home':0.8}],NOW)
        self.assertFalse(r['verified_positive_ev'])
        self.assertFalse(r['calibrated_model'])

    def test_invalid_input_is_not_silently_assumed(self):
        with self.assertRaisesRegex(ValueError,'INVALID_SHADOW_DIAGNOSTIC_INPUT'):
            summarize({}, [], NOW)
        with self.assertRaisesRegex(ValueError,'INVALID_SHADOW_DIAGNOSTIC_INPUT'):
            summarize([], [], datetime(2026,11,23,12,0))

if __name__ == '__main__':
    unittest.main()
