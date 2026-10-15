import hashlib
import json
import unittest
from openfootball_ft_normalizer import normalize

class OpenFootballNormalizerTests(unittest.TestCase):
    def test_ft_date_only_never_fakes_kickoff(self):
        raw=json.dumps({"matches":[{"date":"2026-10-10","team1":"A","team2":"B","score":{"ft":[2,1]}}]}).encode()
        rows=normalize(raw,"https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json","2026-10-15T00:00:00Z")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["score_ft"],[2,1])
        self.assertIsNone(rows[0]["kickoff_utc"])
        self.assertEqual(rows[0]["kickoff_precision"],"DATE_ONLY")
        self.assertEqual(rows[0]["raw_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertFalse(rows[0]["independently_verified"])
    def test_no_ft_or_invalid_scores(self):
        raw=json.dumps({"matches":[{"date":"2026-10-10","team1":"A","team2":"B"},
          {"date":"2026-10-10","team1":"A","team2":"B","score":{"ft":[-1,1]}},
          {"date":"2026-10-10","team1":"A","team2":"B","score":{"ft":[1,True]}}]}).encode()
        self.assertEqual(normalize(raw,"https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json","2026-10-15T00:00:00Z"),[])
    def test_invalid_schema(self):
        with self.assertRaises(ValueError):
            normalize(b"[]","https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json","2026-10-15T00:00:00Z")
if __name__=="__main__":
    unittest.main()
