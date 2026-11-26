import json
import ssl
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import ProxyHandler, HTTPSHandler, Request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vnext_direct_transport_offline import (build_reference_opener, rehearse,
                                           DenyRedirect, URL, MAX_BYTES)


class TransportPolicyTests(unittest.TestCase):
    def run_case(self, **kw):
        params=dict(env={},response_url=URL,status=200,content_type="application/json",
                    body=json.dumps({"errors":[],"response":[{"fixture":{"id":1,"status":{"short":"2H"}},
                         "goals":{"home":1,"away":0}}]}).encode())
        params.update(kw)
        with patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("network forbidden")) as net:
            out=rehearse(**params)
            net.assert_not_called()
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertFalse(out["real_request_authorized"])
        self.assertEqual(out["real_requests"],0)
        return out

    def test_reference_opener_policy(self):
        with patch("vnext_direct_transport_offline.build_opener") as factory:
            build_reference_opener({})
            proxy,https,redirect=factory.call_args.args
            self.assertIsInstance(proxy,ProxyHandler)
            self.assertEqual(proxy.proxies,{})
            self.assertIsInstance(https,HTTPSHandler)
            self.assertTrue(https._context.check_hostname)
            self.assertEqual(https._context.verify_mode,ssl.CERT_REQUIRED)
            self.assertGreaterEqual(https._context.minimum_version,ssl.TLSVersion.TLSv1_2)
            self.assertIsInstance(redirect,DenyRedirect)

    def test_redirect_denied(self):
        for code in (301,302,303,307,308):
            with self.assertRaisesRegex(ValueError,"REDIRECT_REJECTED"):
                DenyRedirect().redirect_request(Request(URL),None,code,"redirect",{},"https://example.invalid")

    def test_proxy_and_trust_overrides(self):
        for key in ("HTTPS_PROXY","http_proxy","ALL_PROXY","no_proxy","SSL_CERT_FILE",
                    "SSL_CERT_DIR","REQUESTS_CA_BUNDLE","CURL_CA_BUNDLE"):
            self.assertEqual(self.run_case(env={key:"synthetic"})["reason"],"POLICY_OR_SCHEMA_REJECTED")

    def test_exact_destination(self):
        for url in (URL+"/",URL.replace("https:","http:"),URL.replace("live=all","live=1"),
                    "https://example.invalid/"):
            self.assertEqual(self.run_case(response_url=url)["reason"],"DESTINATION_MISMATCH")

    def test_status_and_type(self):
        for status in (201,301,401,429,500,True):
            self.assertEqual(self.run_case(status=status)["reason"],"HTTP_STATUS_REJECTED")
        for ct in ("text/html","application/jsonx",None):
            self.assertEqual(self.run_case(content_type=ct)["reason"],"CONTENT_TYPE_REJECTED")

    def test_body_limit_and_type(self):
        for body in (b"",b"x"*(MAX_BYTES+1),"{}",None):
            self.assertEqual(self.run_case(body=body)["reason"],"BODY_SIZE_OR_TYPE_REJECTED")

    def test_malformed_json(self):
        for body in (b'{"errors":[],"errors":[],"response":[]}',b'{"errors":[],"response":[NaN]}',
                     b'not json',b'\xff',b'{"response":[]}'):
            self.assertEqual(self.run_case(body=body)["reason"],"POLICY_OR_SCHEMA_REJECTED")

    def test_valid_synthetic_response_never_authorizes(self):
        out=self.run_case(content_type="application/json; charset=utf-8")
        self.assertEqual(out["reason"],"SYNTHETIC_RESPONSE_ONLY")
        self.assertEqual(out["synthetic_rows"],1)
        self.assertNotIn("offline-fixture-not-a-real-key",str(out))
