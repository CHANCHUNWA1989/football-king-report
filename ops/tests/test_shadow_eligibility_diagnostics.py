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


    def test_generate_reports_every_league_and_keeps_original_probabilities(self):
        from datetime import timedelta
        from ops.shadow_forecast import generate, predict_league
        prior = [
            {'status':'FINISHED', 'date':(NOW-timedelta(days=i+1)).date().isoformat(),
             'home':'Home','away':'Away','score_ft':[1,0]}
            for i in range(40)
        ]
        rows = prior + [fixture()]
        forecast = predict_league(rows, 'epl', NOW)
        self.assertEqual(len(forecast), 1)

        def getter(**kwargs):
            return {'status':'READY_RESEARCH', 'matches':rows,
                    'source':'synthetic', 'captured_utc':NOW.isoformat()}

        report = generate(now=NOW, getter=getter)
        self.assertEqual(report['predictions_count'], 6)
        self.assertEqual(len(report['sources']), 6)
        self.assertEqual(report['predictions'][0]['p_home'], forecast[0]['p_home'])
        self.assertEqual(report['production_recommendations'], 'DISABLED')
        for source in report['sources']:
            detail = source['input_eligibility_diagnostics']
            self.assertEqual(detail['predictions_emitted'], 1)
            self.assertEqual(detail['predictions_retained_at_completion'], 1)
            self.assertEqual(detail['scheduled_valid_precise_utc'], 1)
            self.assertEqual(detail['prior_finished_score_rows'], 40)
            self.assertFalse(detail['verified_positive_ev'])

    def test_generate_zero_model_leagues_explained_without_fake_schedule(self):
        from ops.shadow_forecast import generate
        def getter(**kwargs):
            return {'status':'READY_RESEARCH', 'matches':[fixture(None)],
                    'source':'synthetic'}
        report = generate(now=NOW, getter=getter)
        self.assertEqual(report['predictions_count'], 0)
        self.assertEqual(report['status'], 'HOLD')
        self.assertEqual(len(report['sources']), 6)
        for source in report['sources']:
            detail = source['input_eligibility_diagnostics']
            self.assertEqual(detail['reason'], 'NO_ELIGIBLE_PRECISE_KICKOFF_ROWS')
            self.assertEqual(detail['predictions_retained_at_completion'], 0)
            self.assertEqual(detail['status'], 'HOLD')

if __name__ == '__main__':
    unittest.main()
