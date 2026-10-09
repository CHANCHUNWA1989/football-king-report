"""Three optional API keys are checked privately, without leaks or billing."""
import json
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_secondary_keys import check_all


class FakeResponse:
    def __init__(self, data):
        self.raw = json.dumps(data).encode("utf-8")
    def read(self,length):
        return self.raw[:length]
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False


class SecretCheckTests(unittest.TestCase):
    def test_missing_keys_produce_clear_status_without_any_calls(self):
        called=[]
        def fail(req,timeout):
            called.append(req.full_url)
            raise RuntimeError("SECRETLESS_SHOULD_NOT_CALL")
        result=check_all({},requester=fail)
        self.assertEqual(len(called),0)
        self.assertTrue(all(x["status"]=="NOT_CONFIGURED" for x in result["key_checks"]))
        self.assertFalse(result["credentials_logged"])

    def test_three_tokens_are_only_http_headers_not_json_or_urls(self):
        password="TOP_SECRET_TEST_TOKEN_123456789"
        reqs=[]
        def fake(req,timeout):
            reqs.append(req)
            return FakeResponse({"response":[]})
        inp={"API_FOOTBALL_KEY":password,"FOOTBALL_DATA_ORG_TOKEN":password,
             "SPORTMONKS_API_TOKEN":password}
        value=check_all(inp,requester=fake)
        self.assertEqual(len(reqs),3)
        self.assertTrue(all(x["status"]=="KEY_ACCEPTED" for x in value["key_checks"]))
        self.assertNotIn(password,json.dumps(value))
        self.assertTrue(all(password not in x.full_url for x in reqs))
        self.assertTrue(all(x.full_url.startswith("https://") for x in reqs))

    def test_invalid_key_http401_is_not_printed(self):
        password="TOP_SECRET_TEST_TOKEN_123456789"
        def reject(req,timeout):
            raise HTTPError(req.full_url,401,"test untrusted body",None,None)
        value=check_all({"API_FOOTBALL_KEY":password},requester=reject)
        self.assertEqual(value["key_checks"][0]["status"],"KEY_REJECTED")
        self.assertNotIn(password,json.dumps(value))

    def test_free_plan_denial_is_not_treated_as_success(self):
        def reject(req,timeout):
            raise HTTPError(req.full_url,403,"restricted",None,None)
        value=check_all({"SPORTMONKS_API_TOKEN":"test"},requester=reject)
        self.assertEqual(value["key_checks"][2]["status"],"PLAN_OR_KEY_REJECTED")

    def test_provider_json_errors_are_not_printed(self):
        token="SuperSecretTester"
        def fake(req,timeout):
            return FakeResponse({"errors":{"secret":token}})
        out=check_all({"API_FOOTBALL_KEY":token},requester=fake)
        self.assertEqual(out["key_checks"][0]["status"],"PROVIDER_REJECTED_OR_PLAN_LIMITED")
        self.assertNotIn(token,json.dumps(out))

    def test_429_does_not_trigger_retries(self):
        calls=[]
        def fake(req,timeout):
            calls.append(req.full_url)
            raise HTTPError(req.full_url,429,"limit",None,None)
        out=check_all({"FOOTBALL_DATA_ORG_TOKEN":"test"},requester=fake)
        self.assertEqual(len(calls),1)
        self.assertEqual(out["key_checks"][1]["status"],"FREE_RATE_LIMITED")

    def test_header_newline_never_proceeds(self):
        calls=[]
        def fake(req,timeout):
            calls.append(True)
            return FakeResponse({})
        out=check_all({"SPORTMONKS_API_TOKEN":"malicious\nheader"},requester=fake)
        self.assertEqual(calls,[])
        self.assertEqual(out["key_checks"][2]["status"],"INVALID_PROVIDER_RESPONSE")


if __name__=="__main__":
    unittest.main()
