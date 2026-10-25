"""Supplementary ordered probability scores, never authenticated outcome evidence."""
import copy
import json
import tempfile
from fractions import Fraction
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_center as center
from model_ab import MODEL as B_MODEL, candidate as b_candidate
from model_market_challenger import MODEL as C_MODEL, candidate as c_candidate


class FourWayRPSTests(unittest.TestCase):
    def row(self, y=0):
        p, m = [.7, .2, .1], [.3, .3, .4]
        return dict(league="epl", p=p, m=m, ab=b_candidate(p), ab_model=B_MODEL,
                    c=c_candidate(p, m), c_model=C_MODEL, y=y,
                    kickoff_utc="2026-10-12T12:00:00+00:00",
                    key="synthetic-test-only", production_recommendations="DISABLED",
                    market_utc="2026-10-12T09:00:00+00:00",
                    forecast_utc="2026-10-12T10:00:00+00:00")

    def oracle(self, p, y):
        p = [Fraction(str(v)) for v in p]
        return float(sum((sum(p[:k+1]) - int(y <= k))**2 for k in range(2)) / 2)

    def test_score_matches_independent_fraction_oracle(self):
        for p in ([1, 0, 0], [0, 1, 0], [0, 0, 1], [.2, .3, .5], [1/3]*3):
            for y in range(3):
                with self.subTest(p=p, y=y):
                    self.assertAlmostEqual(center.score_rps(p, y), self.oracle(p, y), places=14)
        self.assertEqual(center.score_rps([0, 0, 1], 0), 1)
        self.assertEqual(center.score_rps([0, 1, 0], 0), .5)

    def test_invalid_inputs_rejected(self):
        for p, y in (([.9,.9,-.8],0), ([.2,.3,.5],True), ([1,0],0),
                     ([float('nan'),0,1],0), ([.2,.3,.5],3), ([True,0,0],0)):
            with self.subTest(p=p,y=y), self.assertRaises(ValueError):
                center.score_rps(p,y)

    def test_same_cases_for_all_four_and_input_unchanged(self):
        rows = [self.row(0), self.row(2)]
        excluded = self.row(1)
        del excluded['c']
        del excluded['c_model']
        original = copy.deepcopy(rows + [excluded])
        result = center.metrics(rows + [excluded])['prospective_four_way_research']
        self.assertEqual(result['same_sealed_case_count'], 2)
        for name, key in (('a','p'), ('b','ab'), ('c','c'), ('market','m')):
            expected = round(sum(self.oracle(r[key],r['y']) for r in rows)/2,6)
            self.assertEqual(result[name+'_rps'], expected)
        self.assertEqual(rows+[excluded], original)
        self.assertEqual(result['rps_outcome_order'], ['home','draw','away'])
        self.assertTrue(result['rps_lower_is_better'])
        self.assertFalse(result['model_advantage_vs_market_proven'])
        self.assertFalse(result['results_independently_verified'])
        self.assertFalse(result['eligible_for_betting_promotion'])
        self.assertEqual(result['production_recommendations'], 'DISABLED')

    def test_missing_or_unsealed_challenger_means_no_four_way_rps(self):
        for field in ('ab', 'c'):
            row = self.row()
            row[field] = [.1,.1,.8]
            result = center.metrics([row])['prospective_four_way_research']
            self.assertEqual(result['same_sealed_case_count'], 0)
            for name in ('a','b','c','market'):
                self.assertIsNone(result[name+'_rps'])
        self.assertIsNone(center.metrics([]))

    def test_existing_scores_and_thresholds_preserved(self):
        row=self.row(2)
        r=center.metrics([row])['prospective_four_way_research']
        for name,key in (('a','p'),('b','ab'),('c','c'),('market','m')):
            ll,bs=center.score(row[key],row['y'])
            self.assertEqual(r[name+'_log_loss'],round(ll,6))
            self.assertEqual(r[name+'_brier'],round(bs,6))
        self.assertEqual(r['remaining_same_case_fixtures_to_300'],299)
        self.assertEqual(r['remaining_week_blocks_to_12'],11)
        self.assertFalse(r['descriptive_coverage_thresholds_met'])

    def test_publish_carries_scores_to_aggregate_and_league_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            site=Path(temporary)
            docs={
                'status.json': {'production_recommendations':'DISABLED','status':'RESEARCH_ONLY'},
                'market_status.json': {'production_recommendations':'DISABLED'},
                'validation.json': {'status':'HOLD'}, 'crosscheck.json': {},
                'league_coverage.json': {'production_recommendations':'DISABLED'},
                'ab_status.json': {'promotion_allowed':False}, 'shadow.json': {},
                'market_comparison.json': {},
            }
            for name,data in docs.items():
                (site/name).write_text(json.dumps(data))
            evidence=site/'synthetic-evidence.json'
            evidence.write_text(json.dumps({'samples':[self.row()], 'n':1,
                                           'checked_utc':'2026-10-13T00:00:00+00:00',
                                           'production_recommendations':'DISABLED'}))
            center.publish(site,evidence)
            report=json.loads((site/'research_center.json').read_text())
            aggregate=report['aggregate_metrics']['prospective_four_way_research']
            league=report['league_cards'][0]['comparison']['prospective_four_way_research']
            self.assertEqual(aggregate['a_rps'],league['a_rps'])
            self.assertIsNone(report['league_cards'][1]['comparison'])
            self.assertFalse(report['calibration_reliable'])
            self.assertFalse(report['prospective_four_way_challenger_promoted'])
            self.assertEqual(report['production_recommendations'],'DISABLED')


if __name__ == '__main__':
    unittest.main()
