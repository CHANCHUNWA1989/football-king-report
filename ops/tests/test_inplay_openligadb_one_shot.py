"""Synthetic one-shot OpenLigaDB HTTP origin capture tests (no network)."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inplay_openligadb_one_shot import (
    capture_once, replay_saved, _endpoint, _validate_raw, _fetch_one,
)
from ops import private_response_capture as capture_private


NOW=datetime(2026,11,23,0,52,tzinfo=timezone.utc)
EVENT_ID=12345
URL="https://api.openligadb.de/getmatchdata/12345"

def response():
    return {
        "matchID":EVENT_ID,"leagueShortcut":"bl1","leagueSeason":2026,
        "matchDateTimeUTC":"2026-11-23T00:00:00Z",
        "matchIsFinished":False,
        "team1":{"teamId":11,"teamName":"Synthetic Home"},
        "team2":{"teamId":22,"teamName":"Synthetic Away"},
        "goals":[],"matchResults":[],
    }

def raw(obj=None):
    return json.dumps(response() if obj is None else obj,
                      separators=(",",":"),sort_keys=True).encode()

def fake_getter(trace, body=None, status=200, media="application/json", final=None):
    def get(url):
        trace.append(url)
        return (raw() if body is None else body,status,media,URL if final is None else final)
    return get

class OneShotOriginTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"private"
        self.root.mkdir(mode=0o700)
    def run_once(self,**kwargs):
        trace=[]
        result=capture_once(EVENT_ID,self.root,
                            getter=kwargs.get("getter",fake_getter(trace)),
                            now=lambda:NOW,
                            )
        return result,trace
    def test_real_transport_shape_synthetic_getter_single_request_and_private_replay(self):
        result,trace=self.run_once()
        self.assertEqual(trace,[URL])
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertTrue(result["local_original_response_bytes_readback_verified"])
        self.assertTrue(result["created_new_private_archive"])
        self.assertFalse(result["transport_externally_attested"])
        self.assertFalse(result["publisher_identity_authenticated"])
        self.assertFalse(result["actual_live_score_verified"])
        self.assertFalse(result["red_cards_available"])
        self.assertFalse(result["eligible_for_model_input"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["certified_forward_samples"],0)
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertEqual(result["source_raw_sha256_unattested"],hashlib.sha256(raw()).hexdigest())
        self.assertIsNone(result["recommendation"])
        filenames=list(self.root.iterdir())
        self.assertEqual(len(filenames),1)
        self.assertEqual(stat.S_IMODE(filenames[0].stat().st_mode),0o600)
        later=replay_saved(self.root,result["archive_sha256_unattested"],now=NOW+timedelta(days=2))
        self.assertEqual(later["status"],"RESEARCH_ONLY")
        self.assertTrue(later["local_original_response_bytes_readback_verified"])
        self.assertFalse(later["transport_externally_attested"])
        self.assertNotIn("Synthetic Home",str(later))

    def test_duplicate_same_capture_is_create_only_no_overwrite(self):
        a,at=self.run_once()
        b,bt=self.run_once()
        self.assertEqual(at,[URL]);self.assertEqual(bt,[URL])
        self.assertEqual(a["archive_sha256_unattested"],b["archive_sha256_unattested"])
        self.assertFalse(b["created_new_private_archive"])
        self.assertEqual(len(list(self.root.iterdir())),1)

    def test_incorrect_native_id_or_wrong_league_or_team_rejected(self):
        for field,value in (("matchID",EVENT_ID+1),("leagueShortcut","bl2"),
                            ("matchIsFinished",True),("matchID",True)):
            data=response();data[field]=value
            trace=[]
            result=capture_once(EVENT_ID,self.root,getter=fake_getter(trace,body=raw(data)),now=lambda:NOW)
            self.assertEqual(result["status"],"HOLD")
            self.assertEqual(trace,[URL])
        data=response();data["team2"]["teamId"]=11
        self.assertEqual(capture_once(EVENT_ID,self.root,getter=fake_getter([],body=raw(data)),now=lambda:NOW)["status"],"HOLD")
        self.assertEqual(len(list(self.root.iterdir())),0)

    def test_wrong_kickoff_and_future_timestamp_rejected(self):
        for stamp in ("2026-11-23T02:00:00Z","2026-11-22T10:00:00Z","2026-11-23T00:00:00"):
            data=response();data["matchDateTimeUTC"]=stamp
            self.assertEqual(capture_once(EVENT_ID,self.root,getter=fake_getter([],body=raw(data)),now=lambda:NOW)["status"],"HOLD")

    def test_redirect_media_non200_and_oversized_response_rejected(self):
        cases=[dict(final="https://api.openligadb.de.evil.test/getmatchdata/12345"),
               dict(status=302),dict(status=429),dict(media="text/html"),
               dict(body=b"X"*250001)]
        for c in cases:
            self.assertEqual(capture_once(EVENT_ID,self.root,getter=fake_getter([],**c),now=lambda:NOW)["status"],"HOLD")
        self.assertEqual(len(list(self.root.iterdir())),0)

    def test_invalid_match_id_disallows_any_request(self):
        for event in (0,-1,True,"12345","1/../../secret",10**20):
            trace=[]
            r=capture_once(event,self.root,getter=fake_getter(trace),now=lambda:NOW)
            self.assertEqual(r["status"],"HOLD")
            self.assertEqual(trace,[])

    def test_duplicate_json_key_and_nonfinite_rejected(self):
        bad=[b'{"matchID":12345,"matchID":12346}',raw().replace(b'"matchID":12345',b'"matchID":NaN')]
        for body in bad:
            self.assertEqual(capture_once(EVENT_ID,self.root,getter=fake_getter([],body=body),now=lambda:NOW)["status"],"HOLD")

    def test_stale_or_corrupt_private_file_detected_on_replay(self):
        result,_=self.run_once()
        path=next(self.root.iterdir())
        path.write_bytes(b"forged")
        self.assertEqual(replay_saved(self.root,result["archive_sha256_unattested"],now=NOW)["status"],"HOLD")
        self.assertEqual(capture_once(EVENT_ID,self.root,getter=fake_getter([]),now=lambda:NOW)["status"],"HOLD")

    def test_symlink_public_mode_git_location_rejected_before_http(self):
        self.root.chmod(0o755)
        trace=[]
        self.assertEqual(capture_once(EVENT_ID,self.root,getter=fake_getter(trace),now=lambda:NOW)["status"],"HOLD")
        self.assertEqual(trace,[])
        self.root.chmod(0o700)
        (Path(self.temp.name)/".git").mkdir()
        self.assertEqual(capture_once(EVENT_ID,self.root,getter=fake_getter(trace),now=lambda:NOW)["status"],"HOLD")
        self.assertEqual(trace,[])

    def test_network_exception_no_secret_leak_and_no_retries(self):
        called=[]
        def fail(url):
            called.append(url)
            raise RuntimeError("USER_SECRET_IN_SOURCE_RESPONSE")
        result=capture_once(EVENT_ID,self.root,getter=fail,now=lambda:NOW)
        self.assertEqual(len(called),1)
        self.assertEqual(result["status"],"HOLD")
        self.assertNotIn("USER_SECRET",str(result))
        self.assertEqual(len(list(self.root.iterdir())),0)

    def test_missing_or_wrong_archive_pin_rejected(self):
        self.assertEqual(replay_saved(self.root,"0"*64,now=NOW)["status"],"HOLD")
        self.assertEqual(replay_saved(self.root,"../../../etc/passwd",now=NOW)["status"],"HOLD")

    def test_quote_or_xg_not_inferred_from_openliga_response(self):
        result,_=self.run_once()
        self.assertIsNone(result["model_probability"])
        self.assertFalse(result["red_cards_available"])
        self.assertFalse(result["odds_or_xg_verified"])
        self.assertFalse(result["two_source_independence_verified"])


if __name__=="__main__":
    unittest.main()
