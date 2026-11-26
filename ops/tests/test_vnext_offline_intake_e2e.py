import concurrent.futures
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vnext_quota_coordinator_contract import State
from vnext_direct_transport_offline import URL
from vnext_offline_intake_e2e import run


class Store:
    def __init__(self):
        self.state = State("test", 0, 0, ())
        self.lock = threading.Lock()
        self.calls = 0

    def read(self):
        with self.lock:
            return self.state

    def cas(self, old, new):
        with self.lock:
            self.calls += 1
            if self.state != old:
                return False
            self.state = new
            return True


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()

    def inputs(self, rid="r"):
        return dict(quota=dict(epoch="test", revision_floor=0, request_id=rid,
                    consumer="runner", now=100000, observed=100000,
                    daily_remaining=100, minute_remaining=10),
                    transport=dict(env={}, response_url=URL, status=200,
                    content_type="application/json", body=json.dumps({"errors":[],
                    "response":[{"fixture":{"id":11,"status":{"short":"2H","elapsed":60}},
                    "goals":{"home":1,"away":0}}]}).encode()),
                    mapping=dict(primary_id=11,secondary_id=22), primary_observed=99990,
                    secondary=dict(fixture_id=22,publisher="synthetic_secondary",
                    observed=99995,phase="2H",minute=60,home=1,away=0))

    def check(self, args):
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("no network")) as net:
            out = run(self.store, **args)
            net.assert_not_called()
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["production_recommendations"], "DISABLED")
        self.assertEqual(out["real_requests"], 0)
        for k in ("real_request_authorized","source_authenticated","actual_xg_verified",
                  "actual_live_odds_verified","positive_ev_verified"):
            self.assertIs(out[k], False)
        return out

    def test_complete_synthetic_path(self):
        out = self.check(self.inputs())
        self.assertEqual(out["stage"], "COMPLETE")
        self.assertTrue(out["synthetic_scoreboard_agreement"])
        self.assertTrue(out["simulated_reservation"])

    def test_quota_failure_short_circuits(self):
        a = self.inputs()
        a["quota"]["daily_remaining"] = 1
        with patch("vnext_offline_intake_e2e.rehearse") as transport:
            out = self.check(a)
            transport.assert_not_called()
        self.assertEqual(out["stage"],"QUOTA")
        self.assertFalse(out["simulated_reservation"])

    def test_transport_failure_burns_reservation(self):
        a = self.inputs()
        a["transport"]["response_url"] = "https://example.invalid/"
        self.assertEqual(self.check(a)["stage"], "TRANSPORT")
        self.assertEqual(self.check(self.inputs())["reason"], "REPLAY")
        self.assertEqual(len(self.store.state.attempts), 1)

    def test_proxy_and_malformed_body_reject(self):
        for i, changes in enumerate((dict(env={"HTTPS_PROXY":"synthetic"}),
                                      dict(body=b"not json"),dict(status=302))):
            a = self.inputs(str(i))
            a["transport"].update(changes)
            self.assertEqual(self.check(a)["stage"], "TRANSPORT")

    def test_stale_future_and_skew(self):
        for i, (primary, secondary) in enumerate(((99939,99990),(100001,99990),(99940,99971))):
            a = self.inputs(str(i))
            a["primary_observed"] = primary
            a["secondary"]["observed"] = secondary
            self.assertEqual(self.check(a)["reason"], "CLOCK_REJECTED")

    def test_identity_and_source(self):
        for i, (key, value, reason) in enumerate((
            ("fixture_id",23,"IDENTITY_MISMATCH"),
            ("publisher","primary","SOURCE_LABEL_REJECTED"),
            ("home",True,"MALFORMED_INPUT"))):
            a = self.inputs(str(i))
            a["secondary"][key] = value
            self.assertEqual(self.check(a)["reason"], reason)

    def test_score_minute_phase_disagreement(self):
        for i,(key,value) in enumerate((("home",2),("minute",61),("phase","HT"))):
            a = self.inputs(str(i))
            a["secondary"][key] = value
            self.assertEqual(self.check(a)["reason"],"STATE_MISMATCH")

    def test_primary_identity_bound_to_payload(self):
        a = self.inputs()
        a["mapping"]["primary_id"] = 12
        self.assertEqual(self.check(a)["reason"], "PRIMARY_ID_MISSING")

    def test_ambiguous_commit_stops_transport(self):
        original = self.store.cas
        def uncertain(old,new):
            original(old,new)
            raise TimeoutError()
        self.store.cas = uncertain
        with patch("vnext_offline_intake_e2e.rehearse") as transport:
            out = self.check(self.inputs())
            transport.assert_not_called()
        self.assertEqual(out["stage"],"QUOTA")
        self.assertEqual(len(self.store.state.attempts),1)
        self.assertEqual(self.check(self.inputs())["reason"],"REPLAY")

    def test_parallel_intake_limit(self):
        # Patch once outside the threads so mocks cannot race during teardown.
        with patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("no network")) as net:
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                rows = list(pool.map(lambda n: run(self.store,**self.inputs(str(n))),range(64)))
            net.assert_not_called()
        accepted = sum(r["synthetic_scoreboard_agreement"] for r in rows)
        self.assertTrue(1 <= accepted <= 9)
        self.assertEqual(accepted,len(self.store.state.attempts))
        self.assertTrue(all(r["status"]=="HOLD" and r["real_requests"]==0 and
                            r["real_request_authorized"] is False for r in rows))
