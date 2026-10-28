"""Inclusive decimal sum boundaries; scores never normalize sealed vectors."""
import copy
from decimal import Decimal, localcontext
import itertools
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_center import score, score_rps


class ProbabilitySumBoundaryTests(unittest.TestCase):
    def assert_scores_unchanged(self, probabilities):
        before = copy.deepcopy(probabilities)
        for outcome in range(3):
            expected = (-math.log(max(probabilities[outcome], 1e-15)),
                        sum((p-int(i == outcome))**2 for i,p in enumerate(probabilities)))
            self.assertEqual(score(probabilities, outcome), expected)
            expected_rps = ((probabilities[0]-int(outcome == 0))**2
                            +(probabilities[0]+probabilities[1]-int(outcome <= 1))**2)/2
            self.assertEqual(score_rps(probabilities, outcome), expected_rps)
        self.assertEqual(probabilities, before)

    def test_inclusive_decimal_endpoints_in_every_outcome_order(self):
        for p in ([.998,0,0], [1,.002,0], [.4,.3,.298], [.4,.3,.302]):
            for permutation in set(itertools.permutations(p)):
                with self.subTest(p=permutation):
                    self.assert_scores_unchanged(list(permutation))

    def test_one_float_step_outside_endpoint_is_rejected(self):
        for p in ([math.nextafter(.998,0),0,0],
                  [1,math.nextafter(.002,math.inf),0],
                  [.4,.3,math.nextafter(.298,0)],
                  [.4,.3,math.nextafter(.302,math.inf)]):
            for permutation in set(itertools.permutations(p)):
                for scorer in (score,score_rps):
                    with self.subTest(p=permutation,scorer=scorer.__name__), self.assertRaisesRegex(
                            ValueError,'INVALID_SCORE_INPUT'):
                        scorer(list(permutation),0)

    def test_inside_neighbors_and_ordinary_vectors_preserve_exact_scores(self):
        for p in ([math.nextafter(.998,1),0,0],
                  [1,math.nextafter(.002,0),0], [.2,.3,.5], [1/3]*3,
                  [1,0,0], [0,1,0], [0,0,1], [.9981,0,0], [1,.0019,0]):
            self.assert_scores_unchanged(p)

    def test_subnormal_tail_does_not_hide_a_real_decimal_boundary_crossing(self):
        tiny=math.nextafter(0,1)
        self.assert_scores_unchanged([.998,tiny,0])
        for p in ([1,.002,tiny], [math.nextafter(.998,0),tiny,0]):
            for scorer in (score,score_rps):
                with self.assertRaises(ValueError):scorer(p,0)

    def test_decimal_oracle_for_finite_grid_around_both_boundaries(self):
        with localcontext() as context:
            context.prec=1100
            for tail in (.2979999,.298,.2980001,.3019999,.302,.3020001):
                p=[.4,.3,tail]
                total=sum((Decimal(str(x)) for x in p),Decimal(0))
                accepted=Decimal('.998') <= total <= Decimal('1.002')
                for scorer in (score,score_rps):
                    if accepted:self.assert_scores_unchanged(p)
                    else:
                        with self.subTest(p=p,scorer=scorer.__name__),self.assertRaises(ValueError):
                            scorer(p,0)

    def test_json_round_trip_does_not_rewrite_or_normalize_probabilities(self):
        for raw in ('[0.4,0.3,0.298]','[0.4,0.3,0.302]'):
            p=json.loads(raw)
            serialized=json.dumps(p)
            self.assert_scores_unchanged(p)
            self.assertEqual(json.dumps(p),serialized)

    def test_existing_type_range_and_outcome_guards_stay_strict(self):
        for p,y in (([True,0,0],0),([.2,.3,.5],True),([.2,.3,.5],3),
                    ([float('nan'),0,1],0),([float('inf'),0,0],0),
                    ([1.001,0,0],0),([-.001,.5,.5],0),([.2,.3],0),
                    ((.2,.3,.5),0),([.9979999,0,0],0),([1,.0020001,0],0)):
            for scorer in (score,score_rps):
                with self.subTest(p=p,y=y,scorer=scorer.__name__),self.assertRaises(ValueError):
                    scorer(p,y)


if __name__=='__main__':unittest.main()
