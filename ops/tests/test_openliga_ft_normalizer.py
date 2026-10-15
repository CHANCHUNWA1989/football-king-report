import hashlib
import json
import unittest
from datetime import datetime,timezone
from openliga_ft_normalizer import normalize

class NormalizerTests(unittest.TestCase):
    def test_ft_and_raw_provenance(self):
        data=[{"matchID":12,"matchIsFinished":True,"team1":{"teamName":"A"},"team2":{"teamName":"B"},
          "matchDateTimeUTC":"2026-10-01T12:00:00Z","matchResults":[{"resultTypeID":1,"pointsTeam1":0,"pointsTeam2":0},
          {"resultTypeID":2,"pointsTeam1":2,"pointsTeam2":1}]}]
        raw=json.dumps(data).encode()
        rows=normalize(raw,"https://api.openligadb.de/getmatchdata/bl1/2026","2026-10-15T00:00:00Z")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["score_ft"],[2,1])
        self.assertEqual(rows[0]["raw_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertFalse(rows[0]["independently_verified"])
    def test_unfinished_and_missing_fulltime_rejected(self):
        base={"matchIsFinished":False,"team1":{"teamName":"A"},"team2":{"teamName":"B"},
          "matchDateTimeUTC":"2026-10-01T12:00:00Z","matchResults":[{"resultTypeID":2,"pointsTeam1":1,"pointsTeam2":0}]}
        raw=json.dumps([base,{**base,"matchIsFinished":True,"matchResults":[]}]).encode()
        self.assertEqual(normalize(raw,"https://api.openligadb.de/getmatchdata/bl1/2026","2026-10-15T00:00:00Z"),[])
    def test_bad_schema_and_time_rejected(self):
        with self.assertRaises(ValueError):
            normalize(b"{}","https://api.openligadb.de/getmatchdata/bl1/2026","2026-10-15T00:00:00Z")
        with self.assertRaises(ValueError):
            normalize(b"[]","https://api.openligadb.de/getmatchdata/bl1/2026","2026-10-15T00:00:00")
if __name__=="__main__":
    unittest.main()
