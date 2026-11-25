import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vnext_api_football_live_probe import probe,summarize,quota_preflight,URL
from datetime import datetime, timezone, timedelta

def sample():
    return {"errors":[],"response":[{"fixture":{"id":1,"status":{"short":"2H"}},
                                      "goals":{"home":1,"away":0}}]}
class ProbeTests(unittest.TestCase):
    def test_default_and_missing_key_no_calls(self):
        with patch("vnext_api_football_live_probe.fetch") as f:
            self.assertEqual(probe(key="test")["requests_attempted"],0)
            self.assertEqual(probe(key="",allow=True)["reason"],"NOT_CONFIGURED")
            f.assert_not_called()
    def test_single_call_and_no_certification(self):
        with patch("vnext_api_football_live_probe.fetch",return_value=(sample(),"OK")) as f:
            injected=lambda *a, **k: None
            out=probe(key="synthetic",allow=True,requester=injected)
            f.assert_called_once_with("api_football",URL,{"x-apisports-key":"synthetic"},requester=injected)
            self.assertEqual(out["claimed_live_score_rows"],1)
            self.assertEqual(out["status"],"HOLD")
            self.assertFalse(out["upstream_timestamp_verified"])
            self.assertFalse(out["positive_ev_verified"])
            self.assertNotIn("synthetic",str(out))
    def test_denied_and_rate_limit_no_retry(self):
        for status in ("KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","RATE_LIMITED"):
            with patch("vnext_api_football_live_probe.fetch",return_value=(None,status)) as f:
                self.assertEqual(probe(key="x",allow=True,requester=lambda *a, **k: None)["reason"],status)
                f.assert_called_once()
    def test_duplicates_and_bad_score(self):
        b=sample()
        b["response"]*=2
        with self.assertRaises(ValueError):
            summarize(b)
        b=sample()
        b["response"][0]["goals"]["home"]=True
        with self.assertRaises(ValueError):
            summarize(b)
    def test_provider_errors(self):
        with self.assertRaises(ValueError):
            summarize({"errors":{"plan":"denied"},"response":[]})

class ProbeTransportTests(unittest.TestCase):
    """Exercise actual shared fetch with a synthetic HTTP transport; no network."""
    def test_exact_url_and_one_transport_call(self):
        import json
        from unittest.mock import MagicMock
        requester=MagicMock()
        requester.return_value.__enter__.return_value.read.return_value=json.dumps(sample()).encode()
        out=probe(key="synthetic-key",allow=True,requester=requester)
        requester.assert_called_once()
        req=requester.call_args.args[0]
        self.assertEqual(req.full_url,URL)
        self.assertEqual(req.get_method(),"GET")
        self.assertEqual(req.get_header("X-apisports-key"),"synthetic-key")
        self.assertEqual(requester.call_args.kwargs["timeout"],13)
        self.assertEqual(out["claimed_live_score_rows"],1)
        self.assertEqual(out["requests_attempted"],1)
        self.assertEqual(out["production_recommendations"],"DISABLED")

    def test_transport_http_failures_never_retry(self):
        from urllib.error import HTTPError
        from unittest.mock import Mock
        for code,reason in ((401,"KEY_REJECTED"),(403,"PLAN_OR_LEAGUE_RESTRICTED"),
                            (429,"RATE_LIMITED"),(500,"HTTP_ERROR")):
            with self.subTest(code=code):
                requester=Mock(side_effect=HTTPError(URL,code,"synthetic",None,None))
                out=probe(key="synthetic-key",allow=True,requester=requester)
                requester.assert_called_once()
                self.assertEqual(out["reason"],reason)
                self.assertEqual(out["requests_attempted"],1)
                self.assertEqual(out["claimed_live_score_rows"],0)

    def test_transport_timeout_never_retry(self):
        from unittest.mock import Mock
        requester=Mock(side_effect=TimeoutError("synthetic"))
        out=probe(key="synthetic-key",allow=True,requester=requester)
        requester.assert_called_once()
        self.assertEqual(out["reason"],"NETWORK_ERROR")
        self.assertEqual(out["requests_attempted"],1)

    def test_transport_bad_json_never_retry(self):
        from unittest.mock import MagicMock
        requester=MagicMock()
        requester.return_value.__enter__.return_value.read.return_value=b"not json"
        out=probe(key="synthetic-key",allow=True,requester=requester)
        requester.assert_called_once()
        self.assertEqual(out["reason"],"INVALID_DATA")
        self.assertEqual(out["claimed_live_score_rows"],0)

    def test_default_transport_rejects_redirect_without_network(self):
        from unittest.mock import Mock
        from urllib.request import Request
        def fake_build(handler):
            with self.assertRaisesRegex(ValueError,"PROVIDER_REDIRECT_REJECTED"):
                handler.redirect_request(Request(URL),None,302,"synthetic",{},
                                         "https://example.invalid/")
            return Mock(open=Mock(side_effect=ValueError("PROVIDER_REDIRECT_REJECTED")))
        with patch("urllib.request.build_opener",side_effect=fake_build) as factory:
            from secondary_sources import NoRedirect
            out=probe(key="synthetic-key",allow=True,requester=NoRedirect())
            factory.assert_called_once()
        self.assertEqual(out["reason"],"INVALID_DATA")
        self.assertEqual(out["requests_attempted"],1)


class HardeningTests(unittest.TestCase):
    def test_real_transport_is_disabled_even_with_confirmation(self):
        with patch("vnext_api_football_live_probe.fetch") as f:
            out=probe(key="synthetic",allow=True)
            self.assertEqual(out["requests_attempted"],0)
            self.assertEqual(out["reason"],"LIVE_TRANSPORT_DISABLED_PENDING_QUOTA_CONTROL")
            self.assertEqual(out["production_recommendations"],"DISABLED")
            f.assert_not_called()

    def test_strict_rows_no_silent_partial_acceptance(self):
        for bad in (None, {}, {"fixture":{"id":True}}, {"fixture":{"id":2,"status":{"short":[]}}}, {"fixture":{"id":2,"status":{"short":"FT"}},"goals":{"home":1,"away":0}}):
            with self.subTest(bad=bad):
                b=sample(); b["response"].append(bad)
                with self.assertRaises(ValueError): summarize(b)

    def test_missing_or_malformed_errors_field(self):
        for v in (None, "", False, 0):
            b=sample(); b["errors"]=v
            with self.assertRaises(ValueError): summarize(b)
        b=sample(); del b["errors"]
        with self.assertRaises(ValueError): summarize(b)
        self.assertEqual(summarize({"errors":[],"response":[]}),(0,0))

    def test_quota_evidence_clock_and_reserve(self):
        now=datetime(2026,11,25,10,0,tzinfo=timezone.utc)
        good={"observed_utc":now.isoformat(),"daily_remaining":50,"minute_remaining":5,"plan":"FREE"}
        self.assertTrue(quota_preflight(good,now=now))
        for delta in (timedelta(seconds=1),timedelta(minutes=-5,seconds=-1)):
            self.assertFalse(quota_preflight(dict(good,observed_utc=(now+delta).isoformat()),now=now))
        for field,value in (("daily_remaining",1),("minute_remaining",1),("minute_remaining",True),("daily_remaining",101),("plan","PAID"),("observed_utc","2026-11-25T10:00:00")):
            with self.subTest(field=field,value=value):
                self.assertFalse(quota_preflight(dict(good,**{field:value}),now=now))
        self.assertFalse(quota_preflight(None,now=now))
        self.assertTrue(quota_preflight(dict(good,observed_utc=(now-timedelta(minutes=5)).isoformat(),daily_remaining=2,minute_remaining=2),now=now))
