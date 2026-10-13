import unittest
from shadow_verified_adapter import verified_record
from shadow_four_model_audit import evaluate

SEALED = {"fixture_id":"f1","kickoff_utc":"2026-10-12T12:00:00Z",
          "sealed_at_utc":"2026-10-12T10:00:00Z",
          "market_snapshot_utc":"2026-10-12T09:30:00Z",
          "model":[0.6,0.2,0.2],"market":[0.4,0.3,0.3]}

def observation(provider, group, home=2, away=1):
    return {"fixture_id":"f1","status":"FT","provider_id":provider,
            "independent_group_id":group,"published_utc":"2026-10-12T15:00:00Z",
            "home_goals":home,"away_goals":away}

class AdapterTests(unittest.TestCase):
    def test_independent_agreement(self):
        row=verified_record(SEALED,[observation("a","g1"),observation("b","g2")])
        self.assertIsNotNone(row)
        self.assertEqual(evaluate([row])["valid_fixtures"],1)

    def test_single_source_is_hold(self):
        self.assertIsNone(verified_record(SEALED,[observation("a","g1")]))

    def test_same_origin_is_not_independent(self):
        self.assertIsNone(verified_record(SEALED,[observation("a","g1"),observation("b","g1")]))

    def test_conflicting_ft_is_hold(self):
        self.assertIsNone(verified_record(SEALED,[observation("a","g1"),observation("b","g2",0,1)]))

    def test_late_market_is_not_scored(self):
        sealed=dict(SEALED,market_snapshot_utc="2026-10-12T11:00:00Z")
        row=verified_record(sealed,[observation("a","g1"),observation("b","g2")])
        self.assertEqual(evaluate([row])["valid_fixtures"],0)

if __name__=="__main__":
    unittest.main()
