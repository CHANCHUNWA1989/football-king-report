import unittest
from datetime import timedelta
from ops.v30_player_lineup import estimate,history,derive,adjust,evaluate,enc,sha
from ops.v6_forward_bundle import utc
CUT=utc("2025-09-01T12:00:00Z")
def observations():
    return [(str(i+1),CUT-timedelta(days=7*(i+1)),CUT-timedelta(days=7*(i+1),hours=-3),90,.5) for i in range(3)]
class PlayerLineupTests(unittest.TestCase):
    def test_prior_only_and_shrinkage(self):
        rows=observations()
        base=estimate(rows,CUT,"99")
        self.assertGreater(base[0],0);self.assertLess(base[0],.5)
        extra=[("99",CUT-timedelta(days=2),CUT-timedelta(days=1),90,1.),("10",CUT-timedelta(days=1),CUT+timedelta(seconds=1),90,1.),("11",CUT-timedelta(hours=3),CUT-timedelta(minutes=1),90,1.)]
        self.assertEqual(estimate(rows+extra,CUT,"99"),base)
    def test_sparse_history_and_transfer_no_inference(self):
        self.assertIsNone(estimate(observations()[:2],CUT,"99"))
        side={"team_id":"1","expected_xi_utc":CUT.isoformat(),"expected_xi":[str(i) for i in range(1,12)],"confirmed_xi":[str(i) for i in range(1,12)]}
        self.assertIsNone(derive(side,{("2",str(i)):observations() for i in range(1,12)},"99"))
    def test_duplicate_and_late_rating(self):
        r={"match_id":"1","team_id":"2","player_id":"3","kickoff_utc":(CUT-timedelta(days=1)).isoformat(),"available_utc":CUT.isoformat(),"minutes":90,"rating":.5}
        d={"schema":"v30-player-history-v1","provider":"test","league":"de.1","rating_definition":"PROVIDER_NORMALIZED_SIGNED_CONTRIBUTION_V1","captured_utc":CUT.isoformat(),"rows":[r,r]}
        raw=enc(d)
        with self.assertRaisesRegex(ValueError,"CLOCK_OR_DUPLICATE"):history(raw,sha(raw),"test","de.1",CUT)
        d["rows"]=[{**r,"available_utc":(CUT+timedelta(seconds=1)).isoformat()}];raw=enc(d)
        with self.assertRaisesRegex(ValueError,"CLOCK_OR_DUPLICATE"):history(raw,sha(raw),"test","de.1",CUT)
    def test_anchor_fallback_and_mass(self):
        r={"stack":[.5,.3,.2],"rating_delta":.3}
        self.assertEqual(adjust(r,0.),r["stack"])
        self.assertGreater(adjust(r,1.)[0],r["stack"][0])
        self.assertAlmostEqual(sum(adjust(r,2.)),1.)
        self.assertEqual(adjust({**r,"rating_delta":0.},2.),r["stack"])
    def test_insufficient_actual_data_abstains(self):
        r=evaluate([],100,12)
        self.assertIsNone(r["metrics"]);self.assertEqual(r["missing_player_history"],12)
        self.assertEqual(r["verified_forward_sample_credit"],0)
