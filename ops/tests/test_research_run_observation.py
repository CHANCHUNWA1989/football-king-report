"""Prospective workflow observation: research decisions, never chat attestations."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_run_observation import build, publish


NOW = datetime(2026, 11, 2, 10, tzinfo=timezone.utc)


def sample():
    return {
        "schema": "football-king-explainable-research-selections-v1",
        "as_of_utc": (NOW - timedelta(seconds=10)).isoformat(),
        "status": "RESEARCH_ONLY",
        "production_recommendations": "DISABLED",
        "automatic_bets": False, "value_recommendation_count": 0,
        "selected_count": 1, "review_count": 1, "model_only_count": 1,
        "selections": [{"case_id": "a", "league": "bundesliga",
                         "kickoff_utc": (NOW+timedelta(hours=2)).isoformat(),
                         "prediction_utc": (NOW-timedelta(minutes=3)).isoformat(),
                         "direction": "HOME", "value_bet_verified": False,
                         "executable_market_odds_available": False,
                         "production_recommendations": "DISABLED"}],
        "reviews": [{"case_id": "b", "league": "bundesliga",
                     "kickoff_utc": (NOW+timedelta(minutes=45)).isoformat(),
                     "prediction_utc": (NOW-timedelta(minutes=3)).isoformat(),
                     "direction": "AWAY", "value_bet_verified": False,
                         "executable_market_odds_available": False,
                         "production_recommendations": "DISABLED"}],
        "model_only_watchlist": [{"event_id": "c", "league": "epl",
                     "kickoff_utc": (NOW+timedelta(hours=3)).isoformat(),
                     "prediction_utc": (NOW-timedelta(minutes=3)).isoformat(),
                     "direction": "DRAW", "value_bet_verified": False,
                         "executable_market_odds_available": False,
                         "production_recommendations": "DISABLED"}],
    }


class ResearchObservationTests(unittest.TestCase):
    def run_build(self, doc):
        raw = json.dumps(doc).encode()
        return build(raw, run_id="1234", attempt="2",
                     sha="a" * 40, now=NOW)

    def test_actual_run_observation_never_qualifies_formal_bet(self):
        data = self.run_build(sample())
        self.assertEqual(data["observed_count"], 3)
        self.assertEqual(data["eligible_at_observation_count"], 2)
        self.assertEqual(data["observed_group_counts"],
                         {"selections":1,"reviews":1,"model_only_watchlist":1})
        self.assertEqual(data["run_id"], "1234")
        self.assertFalse(data["source_generated_at_observation"])
        self.assertFalse(data["chat_message_timestamps_authenticated"])
        self.assertFalse(data["independent_publication_timestamp_verified"])
        self.assertFalse(data["future_model_skill_proven"])
        self.assertFalse(data["can_enter_formal_settlement_ledger"])
        self.assertEqual(data["production_recommendations"], "DISABLED")
        self.assertEqual([x["eligible_at_observation"] for x in data["observations"]],
                         [True,False,True])

    def test_empty_or_hold_report_also_gets_provenance_record(self):
        doc=sample()
        doc.update(status="HOLD", selected_count=0, review_count=0,
                   model_only_count=0, selections=[], reviews=[],
                   model_only_watchlist=[])
        d=self.run_build(doc)
        self.assertEqual(d["observed_count"],0)
        self.assertEqual(d["status"], "HOLD")
        self.assertEqual(d["source_status"],"HOLD")
        self.assertEqual(d["eligible_at_observation_count"],0)

    def test_reject_fake_and_future_and_unsafe_picks(self):
        doc=sample()
        for mutation in (
            lambda d: d.update(production_recommendations="ENABLED"),
            lambda d: d.update(selected_count=2),
            lambda d: d["selections"][0].update(kickoff_utc="2026-11-02T12:00:00"),
            lambda d: d["selections"][0].update(prediction_utc=(NOW+timedelta(hours=1)).isoformat()),
            lambda d: d["selections"][0].update(direction="OVER"),
            lambda d: d["reviews"][0].update(case_id="a"),
            lambda d: d["selections"][0].update(kickoff_utc="bad"),
        ):
            modified=copy.deepcopy(doc)
            mutation(modified)
            with self.assertRaises(ValueError):
                self.run_build(modified)

    def test_reject_invalid_run_identity(self):
        for runid, attempt, sha in (("01","1","a"*40),
                                    ("123","0","a"*40),
                                    ("123","1","bad"),("false","1","a"*40)):
            with self.assertRaises(ValueError):
                build(json.dumps(sample()).encode(),run_id=runid,
                      attempt=attempt,sha=sha,now=NOW)

    def test_preserve_exact_bytes_and_digest_without_modifying_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/"source.json"
            raw=(json.dumps(sample(),ensure_ascii=False,indent=3)+"\n").encode()
            src.write_bytes(raw)
            dst=root/"snapshot"
            result=publish(src,dst,run_id="30",attempt="1",sha="a"*40,now=NOW)
            self.assertEqual(src.read_bytes(),raw)
            self.assertEqual((dst/"research_selections.json").read_bytes(),raw)
            self.assertEqual(result["research_selections_sha256"],hashlib.sha256(raw).hexdigest())
            self.assertEqual(json.loads((dst/"observation.json").read_text())["observed_count"],3)
            with self.assertRaises(ValueError):
                publish(src,dst,run_id="30",attempt="1",sha="a"*40,now=NOW)

    def test_workflow_captures_before_upload_and_before_deployment(self):
        workflow=(Path(__file__).resolve().parents[2]
                  /".github/workflows/football-king-iphone.yml").read_text()
        capture=workflow.index("Capture research decisions as run-bound observations")
        upload=workflow.index("Upload run-bound research decision observation")
        publishsite=workflow.index("Upload mobile report and public quality evidence")
        self.assertLess(capture,upload)
        self.assertLess(upload,publishsite)
        self.assertIn("python ops/research_run_observation.py",workflow)
        self.assertIn("name: football-king-research-decision-observation",workflow)
        self.assertIn("retention-days: 90",workflow)


if __name__=="__main__":
    unittest.main()
