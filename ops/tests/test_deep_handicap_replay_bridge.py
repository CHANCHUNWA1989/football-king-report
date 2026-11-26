"""Synthetic capture-to-result contract tests; no actual fixture claims."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_private_capture import capture, _digest
from deep_handicap_replay_bridge import bridge
from test_deep_handicap_private_capture import inputs, NOW

FINAL="2026-11-27T12:00:00+00:00"


def fixture():
    s,q=inputs()
    report=capture(s,q,now=NOW)
    c=report["candidate"]
    m={"candidate_sha256":report["candidate_sha256"],"fixture_id":c["fixture_id"],
       "league":c["league_id"],"home_id":c["home_id"],"away_id":c["away_id"],
       "kickoff_utc":c["kickoff_utc"],"expected_identity_sealed_utc":"2026-11-27T08:01:00Z",
       "gender":"men","provider_event_ids":{"fotmob":"synthetic1","skysports":"synthetic2"},
       "provider_event_urls":{"fotmob":"https://www.fotmob.com/matches/synthetic1",
                              "skysports":"https://www.skysports.com/football/synthetic2"}}
    obs=[]
    for i,provider in enumerate(m["provider_event_ids"]):
        obs.append({**{k:m[k] for k in ("gender","league","home_id","away_id","kickoff_utc")},
                    "provider":provider,"source_event_id":m["provider_event_ids"][provider],
                    "source_url":m["provider_event_urls"][provider],
                    "captured_utc":"2026-11-27T11:59:30Z","source_updated_utc":"2026-11-27T11:59:00Z",
                    "match_status":"FINISHED","result_scope":"REGULATION_90_MINUTES",
                    "score_home":3,"score_away":0,"evidence_sha256":str(i+1)*64})
    return report,m,obs


def run(report,m,obs,**kwargs):
    args=dict(expected_candidate_sha256=report["candidate_sha256"],as_of_utc=FINAL,data_kind="SYNTHETIC")
    args.update(kwargs)
    return bridge(report,m,obs,**args)


class BridgeTests(unittest.TestCase):
    def test_valid_synthetic_pair_no_mutation_or_credit(self):
        r,m,o=fixture()
        original=copy.deepcopy((r,m,o))
        out=run(r,m,o)
        self.assertEqual((r,m,o),original)
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["true_forward_sample_count"],0)
        self.assertFalse(out["external_witness_verified"])
        self.assertEqual(out["evaluation_row"]["data_kind"],"SYNTHETIC")
        self.assertEqual(out["evaluation_row"]["results"][0]["score_ft"],[3,0])
        self.assertEqual(out["evaluation_row"]["baseline"],r["candidate"]["baseline"])

    def test_tampered_digest_or_unsafe_label_rejected(self):
        r,m,o=fixture()
        r["candidate"]["baseline"]["probabilities"]["FULL_WIN"]=.9
        self.assertIsNone(run(r,m,o)["evaluation_row"])
        r,m,o=fixture()
        self.assertIsNone(run(r,m,o,expected_candidate_sha256="0"*64)["evaluation_row"])
        self.assertIsNone(run(r,m,o,data_kind="VERIFIED")["evaluation_row"])

    def test_identity_clock_regulation_and_provider_conflict(self):
        for change in (
            lambda m,o:m.update(expected_identity_sealed_utc="2026-11-27T10:01:00Z"),
            lambda m,o:m.update(fixture_id="other"),
            lambda m,o:o[0].update(score_home=2),
            lambda m,o:o[0].update(result_scope="AFTER_EXTRA_TIME"),
            lambda m,o:o[0].update(evidence_sha256=o[1]["evidence_sha256"]),
            lambda m,o:o[0].update(source_event_id="other"),
            lambda m,o:o[0].update(captured_utc="2026-11-27T12:01:00Z"),
            lambda m,o:o[0].update(source_updated_utc="2026-11-27T11:40:00Z"),
        ):
            r,m,o=fixture()
            change(m,o)
            self.assertIsNone(run(r,m,o)["evaluation_row"])

    def test_rehashed_inconsistent_prediction_rejected(self):
        r,m,o=fixture()
        r["candidate"]["challenger"]["handicap"]=-2
        r["candidate_sha256"]=_digest(r["candidate"])
        m["candidate_sha256"]=r["candidate_sha256"]
        self.assertIsNone(run(r,m,o)["evaluation_row"])
