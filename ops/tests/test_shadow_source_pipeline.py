"""Offline end-to-end contract test: raw bytes -> manifest -> parser -> FT correlation.

Synthetic fixtures are ONLY for CI; never published as historical results.
"""
import json
import tempfile
import unittest
from pathlib import Path
from shadow_raw_source_collector import collect
from shadow_raw_ft_parser import convert
from shadow_ft_correlator import correlate

class PipelineContractTests(unittest.TestCase):
    def test_two_source_synthetic_contract_stays_hold(self):
        openliga=[{"matchIsFinished":True,"team1":{"teamName":"Bayern Munich"},
                   "team2":{"teamName":"Borussia Dortmund"},
                   "matchDateTimeUTC":"2026-10-12T12:00:00",
                   "matchResults":[{"resultTypeID":2,"pointsTeam1":2,"pointsTeam2":1}]}]
        openfootball={"matches":[{"team1":"Bayern Munich","team2":"Borussia Dortmund",
                                  "date":"2026-10-12","score":{"ft":[2,1]}}]}
        payloads={"api.openligadb.de":json.dumps(openliga).encode(),
                  "raw.githubusercontent.com":json.dumps(openfootball).encode()}
        with tempfile.TemporaryDirectory() as folder:
            manifest=collect(2026,folder,getter=lambda url:next(v for k,v in payloads.items() if k in url))
            self.assertEqual([s["status"] for s in manifest["sources"]],["FETCHED_UNVERIFIED"]*2)
            parsed=convert(folder)
            result=correlate(parsed)
            self.assertEqual(len(result["agreements"]),1)
            self.assertFalse(result["independently_verified"])
            self.assertEqual(result["production_recommendations"],"DISABLED")
            self.assertEqual(manifest["status"],"HOLD")
    def test_tampered_raw_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            payloads={"api.openligadb.de":b"[]","raw.githubusercontent.com":b'{"matches":[]}'}
            collect(2026,folder,getter=lambda url:next(v for k,v in payloads.items() if k in url))
            (Path(folder)/"openligadb.json").write_bytes(b"[] ")
            with self.assertRaisesRegex(ValueError,"RAW_HASH_MISMATCH"):
                convert(folder)
if __name__=="__main__":unittest.main()
