"""Synthetic byte pins and reconstruction regressions."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_input_reconstruction import reconstruct,replay
from deep_handicap_private_capture import capture,_digest
from test_deep_handicap_private_capture import inputs,NOW
from test_deep_handicap_replay_bridge import fixture,run,FINAL


def encode(v):
    return json.dumps(v,sort_keys=True,allow_nan=False).encode()


def packed():
    s,q=inputs()
    r,m,o=fixture()
    return [encode(s),encode(q),encode(r)],m,o


def pins(raw):
    return {name:hashlib.sha256(v).hexdigest()
            for name,v in zip(("shadow","quote_report","candidate_report"),raw)}


def check(raw,**kwargs):
    args={"pins":pins(raw),"expected_capture_utc":NOW.isoformat()}
    args.update(kwargs)
    return reconstruct(*raw,**args)


class ReconstructionTests(unittest.TestCase):
    def test_original_inputs_reconstruct_and_bridge(self):
        raw,m,o=packed()
        r=replay(*raw,m,o,pins=pins(raw),expected_capture_utc=NOW.isoformat(),
                 as_of_utc=FINAL,data_kind="SYNTHETIC")
        self.assertTrue(r["input_byte_pins_matched"])
        self.assertTrue(r["formula_reconstruction_matched"])
        self.assertIsNotNone(r["evaluation_row"])
        self.assertEqual(r["true_forward_sample_count"],0)
        self.assertFalse(r["external_witness_verified"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertNotIn("decimal_odds",json.dumps(r))

    def test_rehashed_valid_probability_forgery_rejected(self):
        raw,m,o=packed()
        report=json.loads(raw[2])
        p=report["candidate"]["baseline"]["probabilities"]
        amount=min(p["FULL_LOSS"],.01)
        self.assertGreater(amount,0)
        p["FULL_LOSS"]-=amount
        p["FULL_WIN"]+=amount
        report["candidate_sha256"]=_digest(report["candidate"])
        m["candidate_sha256"]=report["candidate_sha256"]
        # Legacy structural path accepts a valid mass with newly declared pin.
        self.assertIsNotNone(run(report,m,o)["evaluation_row"])
        raw[2]=encode(report)
        r=check(raw)
        self.assertTrue(r["input_byte_pins_matched"])
        self.assertFalse(r["formula_reconstruction_matched"])
        self.assertEqual(r["reason"],"CANDIDATE_FORMULA_MISMATCH")

    def test_byte_pins_and_strict_json(self):
        raw,_,_=packed()
        original=pins(raw)
        raw[0]+=b" "
        self.assertEqual(check(raw,pins=original)["reason"],"INPUT_PIN_MISMATCH")
        raw,_,_=packed()
        raw[0]=b'{"schema":1,"schema":2}'
        self.assertFalse(check(raw)["formula_reconstruction_matched"])
        raw,_,_=packed()
        raw[1]=b'{"number":NaN}'
        self.assertFalse(check(raw)["formula_reconstruction_matched"])
        raw,_,_=packed()
        self.assertFalse(check(raw,pins={})["input_byte_pins_matched"])

    def test_clock_and_full_report_mismatch(self):
        raw,_,_=packed()
        self.assertFalse(check(raw,expected_capture_utc="2026-11-27T09:00:00Z")["formula_reconstruction_matched"])
        r=json.loads(raw[2])
        r["true_forward_sample_count"]=False
        raw[2]=encode(r)
        self.assertEqual(check(raw)["reason"],"CANDIDATE_FORMULA_MISMATCH")

    def test_result_conflict_keeps_reconstructed_candidate_unqualified(self):
        raw,m,o=packed()
        o[0]["score_home"]=2
        r=replay(*raw,m,o,pins=pins(raw),expected_capture_utc=NOW.isoformat(),
                 as_of_utc=FINAL,data_kind="SYNTHETIC")
        self.assertTrue(r["formula_reconstruction_matched"])
        self.assertIsNone(r["evaluation_row"])
        self.assertEqual(r["reason"],"RESULT_BRIDGE_REJECTED")
