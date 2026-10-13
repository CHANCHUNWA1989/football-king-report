import unittest
from shadow_raw_ft_parser import parse_openligadb,parse_openfootball,convert
import json
import tempfile
from pathlib import Path
class ParserTests(unittest.TestCase):
    def test_openligadb_finished(self):
        rows=parse_openligadb([{"matchIsFinished":True,"team1":{"teamName":"A"},"team2":{"teamName":"B"},"matchDateTimeUTC":"2026-10-12T12:00:00","matchResults":[{"resultTypeID":2,"pointsTeam1":2,"pointsTeam2":1}]}])
        self.assertEqual(rows[0]["score_ft"],[2,1])
    def test_openfootball_ft(self):
        rows=parse_openfootball({"matches":[{"team1":"A","team2":"B","date":"2026-10-12","score":{"ft":[1,1]}}]})
        self.assertEqual(rows[0]["score_ft"],[1,1])
    def test_manifest_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            manifest={"status":"HOLD","independently_verified":False,"captured_utc":"2026-10-14T00:00:00Z",
                      "sources":[{"provider":"OpenFootball","status":"FETCHED_UNVERIFIED",
                      "raw_file":"../outside.json","raw_sha256":"a"*64,"source_url":"https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json"}]}
            (root/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"UNSAFE_RAW_FILE_PATH"):
                convert(root)
    def test_unfinished_rejected(self):
        self.assertEqual(parse_openligadb([{"matchIsFinished":False}]),[])
if __name__=="__main__":unittest.main()
