import unittest
from shadow_parsed_observation_ingest import ingest

class IngestTests(unittest.TestCase):
    def test_date_only_never_fabricates_kickoff(self):
        x=ingest([],{"status":"HOLD","independently_verified":False,"production_recommendations":"DISABLED",
                    "sources":[{"provider":"OpenFootball","captured_utc":"2026-10-14T00:00:00Z",
                    "source_url":"https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json","raw_sha256":"a"*64,
                    "records":[{"home":"FC Bayern München","away":"FC Augsburg","date":"2026-10-10","score_ft":[2,1],"status":"FINISHED"}]}]})
        self.assertEqual(x["observations"],[])
        self.assertEqual(x["source_stats"][0]["excluded_date_only_records"],1)
    def test_untrusted_publisher_rejected_before_scoring(self):
        source={"provider":"OpenLigaDB","captured_utc":"2026-10-14T00:00:00Z",
                "source_url":"https://api.openligadb.de.evil.example/ft","raw_sha256":"a"*64,"records":[]}
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_PUBLISHER_ORIGIN"):
            ingest([],{"status":"HOLD","independently_verified":False,"production_recommendations":"DISABLED","sources":[source]})
    def test_bad_digest_rejected_before_scoring(self):
        source={"provider":"OpenLigaDB","captured_utc":"2026-10-14T00:00:00Z",
                "source_url":"https://api.openligadb.de/getmatchdata/bl1/2026","raw_sha256":"fake","records":[]}
        with self.assertRaisesRegex(ValueError,"INVALID_SOURCE_DIGEST"):
            ingest([],{"status":"HOLD","independently_verified":False,"production_recommendations":"DISABLED","sources":[source]})
    def test_date_only_unique_seal_linked_without_source_kickoff(self):
        sealed=[{"fixture_id":"f1","league":"bundesliga","home":"FC Bayern München","away":"FC Augsburg","kickoff_utc":"2026-10-10T13:30:00Z"}]
        source={"provider":"OpenFootball","captured_utc":"2026-10-14T00:00:00Z",
                "source_url":"https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json",
                "raw_sha256":"a"*64,"records":[{"home":"FC Bayern München","away":"FC Augsburg",
                "date":"2026-10-10","score_ft":[2,1],"status":"FINISHED"}]}
        bundle={"status":"HOLD","independently_verified":False,"production_recommendations":"DISABLED","sources":[source]}
        out=ingest(sealed,bundle)
        self.assertEqual(len(out["observations"]),1)
        self.assertIsNone(out["observations"][0]["publisher_kickoff_utc"])
        self.assertEqual(out["observations"][0]["match_linkage"],"EXACT_TEAMS_AND_DATE_ONLY")
        self.assertEqual(out["production_recommendations"],"DISABLED")
        out2=ingest(sealed+sealed,bundle)
        self.assertEqual(out2["observations"],[])
        self.assertEqual(out2["source_stats"][0]["date_only_ambiguous"],1)
    def test_forged_input_rejected(self):
        with self.assertRaises(ValueError):
            ingest([],{"status":"HOLD","independently_verified":True,"production_recommendations":"DISABLED"})
    def test_duplicate_provider_rejected(self):
        source={"provider":"OpenLigaDB","captured_utc":"2026-10-14T00:00:00Z","records":[]}
        with self.assertRaises(ValueError):
            ingest([],{"status":"HOLD","independently_verified":False,"production_recommendations":"DISABLED","sources":[source,source]})
if __name__=="__main__":unittest.main()
