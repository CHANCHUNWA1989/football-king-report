"""Fail-closed manual egress preflight tests; no external HTTP is ever made."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inplay_openligadb_manual_egress import (
    ACK_KEY, ACK_VALUE, inspect_manual_egress, require_manual_egress,
    ManualEgressDenied,
)
from inplay_openligadb_one_shot import _fetch_one as match_get
from inplay_openligadb_lastchange_probe import (
    _fetch_one as change_get, probe_once,
)
from inplay_openligadb_conditional_capture import conditional_capture_once
from test_inplay_openligadb_one_shot import EVENT_ID, NOW, fake_getter, URL


class ManualEgressPreflightTests(unittest.TestCase):
    def setUp(self):
        private=tempfile.TemporaryDirectory()
        self.addCleanup(private.cleanup)
        self.root=Path(private.name)/"private"
        self.root.mkdir(mode=0o700)

    def check(self, environ):
        with patch("inplay_openligadb_manual_egress.os.geteuid",return_value=1001):
            return inspect_manual_egress(environ)

    def test_no_explicit_opt_in_is_hold_even_on_local_host(self):
        result=self.check({})
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["reason"],"MISSING_MANUAL_EGRESS_ACKNOWLEDGEMENT")
        self.assertFalse(result["host_firewall_isolation_verified"])
        self.assertFalse(result["cross_host_rate_control_verified"])
        self.assertFalse(result["eligible_for_model_input"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertEqual(result["certified_forward_samples"],0)
        self.assertFalse(result["positive_ev_verified"])

    def test_exact_ack_is_procedural_not_firewall_certification(self):
        result=self.check({ACK_KEY:ACK_VALUE})
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertEqual(result["reason"],"LOCAL_MANUAL_EGRESS_CHECK_ONLY")
        self.assertFalse(result["host_firewall_isolation_verified"])
        self.assertFalse(result["cross_host_rate_control_verified"])
        self.assertFalse(result["source_authenticated"])
        self.assertFalse(result["production_http_isolation_certified"])
        self.assertFalse(result["eligible_for_model_input"])

    def test_wrong_ack_or_wrong_case_rejected(self):
        for value in ("", "true", "yes", "one_shot_research_v1", ACK_VALUE+"!"):
            self.assertEqual(self.check({ACK_KEY:value})["status"],"HOLD")

    def test_ci_and_github_runner_flags_rejected_even_if_string_false(self):
        for key in ("CI", "GITHUB_ACTIONS", "GITHUB_RUN_ID", "RUNNER_OS",
                    "ACTIONS_RUNTIME_TOKEN", "GITHUB_TOKEN"):
            with self.subTest(key=key):
                r=self.check({ACK_KEY:ACK_VALUE,key:"false"})
                self.assertEqual(r["reason"],"CI_OR_HOSTED_RUNNER_FORBIDDEN")

    def test_proxy_environment_rejected_including_case_and_no_proxy(self):
        for key in ("HTTPS_PROXY","https_proxy","ALL_PROXY","http_proxy",
                    "NO_PROXY","ftp_proxy"):
            with self.subTest(key=key):
                r=self.check({ACK_KEY:ACK_VALUE,key:"http://proxy.invalid"})
                self.assertEqual(r["reason"],"PROXY_OR_TLS_OVERRIDE_FORBIDDEN")
                self.assertNotIn("proxy.invalid",str(r))

    def test_tls_override_and_keylog_rejected(self):
        for key in ("SSL_CERT_FILE","SSL_CERT_DIR","PYTHONHTTPSVERIFY",
                    "SSLKEYLOGFILE","REQUESTS_CA_BUNDLE","CURL_CA_BUNDLE",
                    "GIT_SSL_NO_VERIFY"):
            with self.subTest(key=key):
                self.assertEqual(self.check({ACK_KEY:ACK_VALUE,key:"secret"})["status"],"HOLD")

    def test_root_user_forbidden_even_with_ack(self):
        with patch("inplay_openligadb_manual_egress.os.geteuid",return_value=0):
            r=inspect_manual_egress({ACK_KEY:ACK_VALUE})
            self.assertEqual(r["reason"],"PRIVILEGED_EXECUTION_FORBIDDEN")

    def test_rejects_invalid_environment_mappings_without_secret_leak(self):
        for env in (None if False else [],{ACK_KEY:2},{ACK_KEY:ACK_VALUE,1:"bad"}):
            result=self.check(env)
            self.assertEqual(result["status"],"HOLD")
            self.assertNotIn("bad",str(result))

    def test_require_raises_only_fixed_code(self):
        with patch.dict(os.environ,{ACK_KEY:"SECRET_SHOULD_NOT_SHOW"},clear=True):
            with self.assertRaises(ManualEgressDenied) as failed:
                require_manual_egress()
        self.assertEqual(str(failed.exception),"MISSING_MANUAL_EGRESS_ACKNOWLEDGEMENT")

    def test_real_probe_path_denied_before_rate_file_or_http_when_no_ack(self):
        with patch.dict(os.environ,{},clear=True):
            with patch("inplay_openligadb_lastchange_probe._fetch_one",
                       side_effect=AssertionError("NETWORK_SHOULD_NOT_BE_CALLED")) as api:
                out=probe_once(2026,8,self.root,now=lambda:NOW)
        self.assertEqual(out["reason"],"MISSING_MANUAL_EGRESS_ACKNOWLEDGEMENT")
        self.assertEqual(out["requests_attempted"],0)
        self.assertEqual(list(self.root.iterdir()),[])
        api.assert_not_called()

    def test_conditional_real_path_denied_before_token_reservation(self):
        with patch.dict(os.environ,{"CI":"true",ACK_KEY:ACK_VALUE},clear=True):
            with patch("inplay_openligadb_conditional_capture._fetch_match",
                       side_effect=AssertionError("NO_NETWORK")) as api:
                out=conditional_capture_once(EVENT_ID,2026,8,self.root,now=lambda:NOW)
        self.assertEqual(out["reason"],"CI_OR_HOSTED_RUNNER_FORBIDDEN")
        self.assertEqual(out["requests_attempted"],0)
        self.assertEqual(list(self.root.iterdir()),[])
        api.assert_not_called()

    def test_low_level_default_http_helpers_also_reject_without_ack(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ManualEgressDenied):
                match_get(URL)
            with self.assertRaises(ManualEgressDenied):
                change_get("https://api.openligadb.de/getlastchangedate/bl1/2026/8")

    def test_injected_synthetic_source_works_without_egress_ack_in_ci(self):
        seen=[]
        with patch.dict(os.environ,{"CI":"true","HTTPS_PROXY":"http://fake.invalid"},clear=True):
            out=probe_once(2026,8,self.root,
                           getter=lambda url: (
                               b'"2026-11-23T00:49:20"',200,"application/json",url),
                           now=lambda:NOW)
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        self.assertFalse(out["eligible_for_model_input"])
        self.assertFalse(out["externally_witnessed"])

    def test_procedural_ack_never_grants_production_status(self):
        out=self.check({ACK_KEY:ACK_VALUE,"HOME":"/temporary/home"})
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        for flag in ("host_firewall_isolation_verified","cross_host_rate_control_verified",
                     "production_http_isolation_certified","source_authenticated",
                     "eligible_for_model_input","positive_ev_verified"):
            self.assertFalse(out[flag])
        self.assertIsNone(out["recommendation"])


if __name__=="__main__":
    unittest.main()
