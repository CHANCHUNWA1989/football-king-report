"""S0 isolated MET Norway weather history+latest and iPhone reader tests.

No provider HTTP, GitHub API traffic, betting, or production writes.
"""
import copy
import gzip
import hashlib
import io
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from met_weather import collect
from met_weather_isolated_archive import (
    BRANCH, REPO, LATEST, WeatherHold, GitHubWeatherStore,
    _blob, publish, read_latest,
)

ROOT=Path(__file__).resolve().parents[2]
NOW=datetime(2026,11,23,10,2,tzinfo=timezone.utc)


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n=-1): return self.data if n<0 else self.data[:n]


def weather(now=NOW):
    next_utc=now.replace(minute=0,second=0,microsecond=0)+timedelta(hours=3)
    next_utc+=timedelta(hours=(-next_utc.hour)%3)
    row={
       "properties":{
          "meta":{"updated_at":(now-timedelta(minutes=8)).isoformat()},
          "timeseries":[{
             "time":(next_utc+timedelta(hours=3*i)).isoformat(),
             "data":{"instant":{"details":{"air_temperature":12.0,"wind_speed":3.5}},
                     "next_1_hours":{"details":{"precipitation_amount":0.2}}}
          } for i in range(9)]
       }
    }
    def fake(req,timeout):
        return Response(json.dumps(row).encode())
    return collect(now=now,client=fake)


def raw_weather(now=NOW):
    return (json.dumps(weather(now),ensure_ascii=False,indent=2)+"\n").encode()


class FakeStore:
    def __init__(self):
        self.files={}
        self.writes=[]
        self.checked=0

    def verify_branch(self):
        self.checked+=1

    def get(self,path):
        return ((self.files[path], _blob(self.files[path]))
                if path in self.files else None)

    def put(self,path,data,*,sha=None):
        old=self.files.get(path)
        if old is not None and (sha is None or sha!=_blob(old)):
            raise WeatherHold("CONCURRENT_WEATHER_ARCHIVE_UPDATE")
        if old is None and sha is not None:
            raise WeatherHold("CONCURRENT_WEATHER_ARCHIVE_UPDATE")
        self.files[path]=data
        self.writes.append((path,sha))


class WeatherIsolatedArchive(unittest.TestCase):
    def test_publish_creates_immutable_history_and_cas_latest(self):
        st=FakeStore()
        r=publish(raw_weather(),run_id="45199901234",attempt="1",store=st,now=NOW)
        self.assertEqual(r["status"],"RESEARCH_ONLY_ARCHIVED")
        self.assertEqual(r["archive_branch"],BRANCH)
        self.assertEqual(len(st.writes),2)
        self.assertTrue(st.writes[0][0].startswith("sources/weather_history/2026/11/23/"))
        self.assertEqual(st.writes[1],(LATEST,None))
        self.assertEqual(st.files[LATEST],raw_weather())
        self.assertEqual(gzip.decompress(st.files[st.writes[0][0]]),raw_weather())
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(read_latest(store=st,now=NOW),raw_weather())

    def test_same_run_identical_replay_is_idempotent(self):
        st=FakeStore()
        publish(raw_weather(),run_id="45199901234",attempt="1",store=st,now=NOW)
        r=publish(raw_weather(),run_id="45199901234",attempt="1",store=st,now=NOW)
        self.assertEqual(r["reason"],"NO_NEW_WEATHER_LATEST")
        self.assertEqual(len(st.writes),2)

    def test_same_history_id_different_bytes_holds_without_overwrite(self):
        st=FakeStore()
        original=raw_weather()
        publish(original,run_id="45199901234",attempt="1",store=st,now=NOW)
        changed=copy.deepcopy(weather())
        changed["cities"][0]["hourly_samples"][0]["temperature_c"]=14
        mutated=(json.dumps(changed,ensure_ascii=False)+"\n").encode()
        with self.assertRaisesRegex(WeatherHold,"WEATHER_HISTORY_IMMUTABLE_COLLISION"):
            publish(mutated,run_id="45199901234",attempt="1",store=st,now=NOW)
        self.assertEqual(st.files[LATEST],original)
        self.assertEqual(len(st.writes),2)

    def test_older_capture_never_downgrades_latest(self):
        st=FakeStore()
        publish(raw_weather(NOW),run_id="45199901234",attempt="1",store=st,now=NOW)
        old=raw_weather(NOW-timedelta(minutes=20))
        outcome=publish(old,run_id="45199901235",attempt="1",store=st,now=NOW)
        self.assertEqual(outcome["reason"],"NO_NEW_WEATHER_LATEST")
        self.assertEqual(st.files[LATEST],raw_weather())
        self.assertEqual(len(st.writes),3)

    def test_newer_capture_cas_updates_only_isolated_branch(self):
        st=FakeStore()
        first=raw_weather()
        publish(first,run_id="45199901234",attempt="1",store=st,now=NOW)
        newer=raw_weather(NOW+timedelta(minutes=9))
        r=publish(newer,run_id="45199901235",attempt="1",store=st,now=NOW+timedelta(minutes=9))
        self.assertEqual(r["reason"],"NEWER_WEATHER_LATEST")
        self.assertEqual(st.files[LATEST],newer)
        self.assertEqual(st.writes[-1],(LATEST,_blob(first)))

    def test_read_latest_missing_tampered_stale_or_denied_holds(self):
        st=FakeStore()
        with self.assertRaises(WeatherHold):
            read_latest(store=st,now=NOW)
        st.files[LATEST]=raw_weather()
        self.assertEqual(read_latest(store=st,now=NOW),raw_weather())
        with self.assertRaisesRegex(WeatherHold,"WEATHER_LATEST_STALE"):
            read_latest(store=st,now=NOW+timedelta(hours=37))
        st.files[LATEST]=b"{}"
        with self.assertRaises(WeatherHold):
            read_latest(store=st,now=NOW)
        class Forbidden(FakeStore):
            def get(self,path):
                raise WeatherHold("WEATHER_GITHUB_API_DENIED")
        with self.assertRaises(WeatherHold):
            read_latest(store=Forbidden(),now=NOW)

    def test_bad_run_id_or_untrusted_schema_rejected_before_write(self):
        st=FakeStore()
        for runid,attempt in (("../main","1"),("0","1"),("1","-1"),("1","999"),("1\n","1")):
            with self.subTest(runid=runid,attempt=attempt),self.assertRaises(WeatherHold):
                publish(raw_weather(),run_id=runid,attempt=attempt,store=st,now=NOW)
        altered=copy.deepcopy(weather())
        altered["production_recommendations"]="ENABLED"
        with self.assertRaises(WeatherHold):
            publish(json.dumps(altered).encode(),run_id="7",attempt="1",store=st,now=NOW)
        self.assertEqual(st.writes,[])

    def test_github_store_must_pin_all_requests_to_archive_and_deny_redirects(self):
        from met_weather_isolated_archive import NoRedirect
        from urllib.request import Request
        for status in (301,302,303,307,308):
            self.assertIsNone(NoRedirect().redirect_request(
                Request("https://api.github.com"),None,status,"moved",{},
                "https://example.invalid/collector"))
        with patch("met_weather_isolated_archive.build_opener") as builder:
            GitHubWeatherStore("synthetic")
        self.assertTrue(any(isinstance(x,NoRedirect) for x in builder.call_args.args))
        store=GitHubWeatherStore("synthetic")
        with self.assertRaisesRegex(WeatherHold,"UNAUTHORIZED_WEATHER_ENDPOINT"):
            store._api("PUT","contents/README.md",data={"branch":"main"})
        with self.assertRaisesRegex(WeatherHold,"WEATHER_WRITE_MUST_TARGET_ISOLATED_BRANCH"):
            store._api("PUT","contents/"+LATEST,data={"branch":"main","content":"dGVzdA=="})
        with self.assertRaisesRegex(WeatherHold,"WEATHER_WRITE_MUST_TARGET_ISOLATED_BRANCH"):
            store._api("PUT","contents/"+LATEST,data={"branch":BRANCH,"content":"dGVzdA==","sha":"not-sha"})

    def test_workflow_and_iphone_consumer_never_read_stale_main(self):
        weatherwf=(ROOT/".github/workflows/football-king-weather.yml").read_text(encoding="utf-8")
        iphone=(ROOT/".github/workflows/football-king-iphone.yml").read_text(encoding="utf-8")
        self.assertIn("ops/met_weather_isolated_archive.py publish",weatherwf)
        self.assertNotIn('gh api -X PUT "repos/$GITHUB_REPOSITORY/contents/',weatherwf)
        self.assertIn("ops/met_weather_isolated_archive.py read",iphone)
        self.assertIn('--input "$RUNNER_TEMP/met-weather-isolated.json"',iphone)
        self.assertNotIn('--input sources/weather_latest.json',iphone)
        self.assertIn("MET_WEATHER_ISOLATED_HOLD",iphone)


if __name__=="__main__":
    unittest.main()
