import unittest
from shadow_raw_ft_parser import parse_openligadb,parse_openfootball,convert
import json
import tempfile
from pathlib import Path
class ParserTests(unittest.TestCase):
    def test_openligadb_finished(self):
        rows=parse_openligadb([{"matchIsFinished":True,"team1":{"teamName":"A"},"team2":{"teamName":"B"},"matchDateTimeUTC":"2026-10-12T12:00:00","matchResults":[{"resultTypeID":2,"pointsTeam1":2,"pointsTeam2":1}]}])
        self.assertEqual(rows[0]["score_ft"],[2,1])
    def test_openligadb_rejects_invalid_ft_and_non_utc(self):
        base={"matchIsFinished":True,"team1":{"teamName":"A"},"team2":{"teamName":"B"},
              "matchDateTimeUTC":"2026-10-12T12:00:00Z",
              "matchResults":[{"resultTypeID":2,"pointsTeam1":2,"pointsTeam2":1}]}
        for bad in (-1,31,True,2.5,"2"):
            row=json.loads(json.dumps(base))
            row["matchResults"][0]["pointsTeam1"]=bad
            with self.subTest(score=bad):
                self.assertEqual(parse_openligadb([row]),[])
        for bad in ("2026-10-12T12:00:00+02:00","not-a-date"):
            row=json.loads(json.dumps(base))
            row["matchDateTimeUTC"]=bad
            with self.subTest(kickoff=bad):
                self.assertEqual(parse_openligadb([row]),[])
    def test_openfootball_ft(self):
        rows=parse_openfootball({"matches":[{"team1":"A","team2":"B","date":"2026-10-12","score":{"ft":[1,1]}}]})
        self.assertEqual(rows[0]["score_ft"],[1,1])
    def test_openfootball_invalid_date_and_team_rejected(self):
        good={"team1":"A","team2":"B","date":"2026-10-12","score":{"ft":[1,1]}}
        for field,value in (("date","2026-02-30"),("date","2026/10/12"),
                            ("date",None),("team1",""),("team2",None)):
            row=dict(good,**{field:value})
            with self.subTest(field=field,value=value):
                self.assertEqual(parse_openfootball({"matches":[row]}),[])
    def test_manifest_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            manifest={"status":"HOLD","independently_verified":False,"captured_utc":"2026-10-14T00:00:00Z","season_start":2026,
                      "sources":[{"provider":"OpenFootball","status":"FETCHED_UNVERIFIED",
                      "raw_file":"../outside.json","raw_sha256":"a"*64,"source_url":"https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json"}]}
            (root/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"UNSAFE_RAW_FILE_PATH"):
                convert(root)
    def test_duplicate_provider_in_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            raw=b'{"matches":[]}'
            import hashlib
            (root/"openfootball.json").write_bytes(raw)
            source={"provider":"OpenFootball","status":"FETCHED_UNVERIFIED",
                    "raw_file":"openfootball.json","raw_sha256":hashlib.sha256(raw).hexdigest(),
                    "source_url":"https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json"}
            manifest={"status":"HOLD","independently_verified":False,"season_start":2026,
                      "captured_utc":"2026-10-14T00:00:00Z","sources":[source,source]}
            (root/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"DUPLICATE_SOURCE_PROVIDER"):
                convert(root)
    def test_manifest_wrong_season_url_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            raw=b'{"matches":[]}'
            import hashlib
            (root/"openfootball.json").write_bytes(raw)
            manifest={"status":"HOLD","independently_verified":False,"season_start":2026,
                      "captured_utc":"2026-10-14T00:00:00Z",
                      "sources":[{"provider":"OpenFootball","status":"FETCHED_UNVERIFIED",
                      "raw_file":"openfootball.json","raw_sha256":hashlib.sha256(raw).hexdigest(),
                      "source_url":"https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/de.1.json"}]}
            (root/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"SOURCE_URL_MISMATCH"):
                convert(root)
    def test_invalid_capture_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for stamp in (None,"not-a-date","2026-10-14T12:00:00",
                          "2026-10-14T12:00:00+08:00"):
                manifest={"status":"HOLD","independently_verified":False,
                          "season_start":2026,"captured_utc":stamp,"sources":[]}
                (root/"manifest.json").write_text(json.dumps(manifest))
                with self.subTest(stamp=stamp),self.assertRaisesRegex(ValueError,"INVALID_CAPTURE_TIMESTAMP"):
                    convert(root)
    def test_malformed_manifest_sources_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            base={"status":"HOLD","independently_verified":False,
                  "season_start":2026,"captured_utc":"2026-10-14T00:00:00Z"}
            for sources,expected in ((None,"INVALID_SOURCE_LIST"),
                                     ({}, "INVALID_SOURCE_LIST"),
                                     ([None],"INVALID_SOURCE_ENTRY"),
                                     ([{"status":"UNKNOWN"}],"UNKNOWN_SOURCE_STATUS"),
                                     ([{}, {}, {}],"INVALID_SOURCE_LIST")):
                manifest=dict(base,sources=sources)
                (root/"manifest.json").write_text(json.dumps(manifest))
                with self.subTest(sources=sources), self.assertRaisesRegex(ValueError,expected):
                    convert(root)
    def test_unfinished_rejected(self):
        self.assertEqual(parse_openligadb([{"matchIsFinished":False}]),[])
if __name__=="__main__":unittest.main()
