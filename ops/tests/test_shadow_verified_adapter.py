import unittest
from shadow_verified_adapter import observation_record, verified_record
from shadow_four_model_audit import evaluate

SEALED = {"fixture_id":"f1","kickoff_utc":"2026-10-12T12:00:00Z",
          "sealed_at_utc":"2026-10-12T10:00:00Z",
          "market_snapshot_utc":"2026-10-12T09:30:00Z",
          "model":[0.6,0.2,0.2],"market":[0.4,0.3,0.3]}

def observation(provider, group, home=2, away=1):
    return {"fixture_id":"f1","status":"FT","provider_id":provider,
            "independent_group_id":group,"published_utc":"2026-10-12T15:00:00Z",
            "home_goals":home,"away_goals":away,
            "source_url":("https://api.openligadb.de/getmatchdata/bl1/2026" if provider=="OpenLigaDB" else "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json"),
            "raw_sha256":"a"*64}

class AdapterTests(unittest.TestCase):
    def test_allowed_urls_and_invented_hashes_cannot_authenticate(self):
        rows = [observation("OpenLigaDB", "openligadb"),
                observation("OpenFootball", "openfootball")]
        for row in rows:
            row.update(result_verified=True, independently_verified=True,
                       raw_provenance_rechecked=True, signature_verified=True)
        self.assertIsNone(verified_record(SEALED, rows))

    def test_consistent_observation_is_preserved_without_becoming_scoreable(self):
        rows = [observation("OpenLigaDB","openligadb"),observation("OpenFootball","openfootball")]
        row=observation_record(SEALED, rows)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "AGREED_UNVERIFIED")
        self.assertEqual(row["result"], [2, 1])
        self.assertEqual(row["recorded_kickoff_utc"], SEALED["kickoff_utc"])
        self.assertIs(row["result_verified"], False)
        self.assertEqual(evaluate([row])["valid_fixtures"], 0)
        self.assertIsNone(verified_record(SEALED, rows))

    def test_unknown_providers_cannot_self_certify(self):
        self.assertIsNone(verified_record(SEALED,[observation('fake-a','fake-group-1'),observation('fake-b','fake-group-2')]))

    def test_missing_raw_evidence_is_hold(self):
        a=observation("OpenLigaDB","openligadb")
        a.pop("raw_sha256")
        self.assertIsNone(observation_record(SEALED,[a,observation("OpenFootball","openfootball")]))
        self.assertIsNone(verified_record(SEALED,[a,observation("OpenFootball","openfootball")]))

    def test_malformed_hash_or_publisher_url_cannot_establish_observation_agreement(self):
        for changes in ({"raw_sha256": "a" * 63}, {"raw_sha256": "g" * 64},
                        {"raw_sha256": True}, {"raw_sha256": "A" * 64},
                        {"source_url": "https://evil.example/ft"},
                        {"provider_id": ["OpenLigaDB"]}):
            with self.subTest(changes=changes):
                a=observation("OpenLigaDB","openligadb")
                a.update(changes)
                rows = [a, observation("OpenFootball","openfootball")]
                self.assertIsNone(observation_record(SEALED, rows))
                self.assertIsNone(verified_record(SEALED, rows))

    def test_single_source_is_hold(self):
        self.assertIsNone(verified_record(SEALED,[observation("OpenLigaDB","openligadb")]))

    def test_same_origin_is_not_independent(self):
        rows = [observation("OpenLigaDB","openligadb"),observation("OpenFootball","openligadb")]
        self.assertIsNone(observation_record(SEALED, rows))
        self.assertIsNone(verified_record(SEALED, rows))

    def test_conflicting_ft_is_hold(self):
        rows = [observation("OpenLigaDB","openligadb"),observation("OpenFootball","openfootball",0,1)]
        self.assertIsNone(observation_record(SEALED, rows))
        self.assertIsNone(verified_record(SEALED, rows))

    def test_late_market_is_not_scored(self):
        sealed=dict(SEALED,market_snapshot_utc="2026-10-12T11:00:00Z")
        row=observation_record(sealed,[observation("OpenLigaDB","openligadb"),observation("OpenFootball","openfootball")])
        self.assertEqual(evaluate([row])["valid_fixtures"],0)

    def test_result_period_conflict_cannot_be_observation_agreement(self):
        a=observation("OpenLigaDB", "openligadb")
        a["result_period"]="EXTRA_TIME"
        self.assertIsNone(observation_record(SEALED, [a, observation("OpenFootball", "openfootball")]))

    def test_boolean_overrides_never_populate_scoring_record(self):
        for sealed in (dict(SEALED, result_verified=True, independently_verified=True),
                       None, {"fixture_id": "f1"}):
            self.assertIsNone(verified_record(sealed, {"verified_records": [SEALED], "verified": True}))

if __name__=="__main__":
    unittest.main()


class TrustedPublisherOriginTests(unittest.TestCase):
    def test_approved_upstream_hosts(self):
        from shadow_verified_adapter import trusted_origin
        self.assertTrue(trusted_origin("OpenLigaDB","https://api.openligadb.de/getmatchdata/bl1/2026"))
        self.assertTrue(trusted_origin("OpenFootball","https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json"))
    def test_forged_and_redirect_style_urls_rejected(self):
        from shadow_verified_adapter import trusted_origin
        for url in ("https://api.openligadb.de.evil.example/a",
                    "https://evil.example/ft",
                    "https://api.openligadb.de@evil.example/ft",
                    "http://api.openligadb.de/ft",
                    "https://api.openligadb.de:444/ft"):
            self.assertFalse(trusted_origin("OpenLigaDB",url),url)
        self.assertFalse(trusted_origin("OpenLigaDB","https://raw.githubusercontent.com/elsewhere"))
        self.assertFalse(trusted_origin("OpenFootball","https://raw.githubusercontent.com/attacker/football.json/master/2026-27/de.1.json"))
        self.assertFalse(trusted_origin("OpenFootball","https://raw.githubusercontent.com/openfootball/other-repo/master/data.json"))
        self.assertFalse(trusted_origin("OpenLigaDB","https://api.openligadb.de/other-endpoint"))
