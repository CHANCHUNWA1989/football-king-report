"""Regression tests for evidence-limited competitive model guard."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from competitive_integrity_guard import (
    SCHEMA, build, enforce_shortlist, publish, render,
)


def fixture(i, *, actual=2, p=None, m=None):
    kickoff = datetime(2026, 10, 10, tzinfo=timezone.utc) + timedelta(days=i)
    return {
        "key": f"case-{i}", "league": "epl",
        "forecast_utc": (kickoff - timedelta(hours=2)).isoformat(),
        "market_utc": (kickoff - timedelta(hours=3)).isoformat(),
        "kickoff_utc": kickoff.isoformat(),
        "p": p or [.8, .1, .1], "m": m or [.2, .3, .5],
        "y": actual,
        "fixture_result_source_independently_verified": False,
        "production_recommendations": "DISABLED",
    }


def ledger(samples):
    return {
        "schema": "football-king-forward-research-1",
        "checked_utc": "2026-12-01T00:00:00+00:00",
        "samples": samples, "n": len(samples),
        "production_recommendations": "DISABLED",
        "results_independently_verified": False,
    }


def shortlist():
    item = {"case_id": "a", "direction": "HOME"}
    return {
        "selections": [item], "selected_count": 1,
        "reviews": [{"case_id": "b"}], "review_count": 1,
        "model_only_watchlist": [{"event_id": "c"}],
        "model_only_count": 1, "fallback_mode": "MODEL_ONLY_LOW_EVIDENCE",
        "fallback_reason": "NO_STRICT_MARKET_MATCHES",
        "diagnostics": {"research_shortlisted": 1, "model_only_watchlist": 1},
        "status": "RESEARCH_ONLY", "reason": "TEST",
        "production_recommendations": "DISABLED",
    }


class CompetitiveGuardTests(unittest.TestCase):
    def test_empty_does_not_invent_competitive_advantage(self):
        r = build(ledger([]))
        self.assertEqual(r["status"], "HOLD")
        self.assertIsNone(r["comparison"])
        self.assertFalse(r["primary_shortlist_veto"])
        self.assertFalse(r["out_of_sample_market_superiority_proven"])
        self.assertEqual(r["recommended_bets"], [])

    def test_on_24_paired_cases_both_market_scores_better(self):
        r = build(ledger([fixture(i) for i in range(24)]))
        self.assertEqual(r["paired_same_fixture_count"], 24)
        self.assertTrue(r["model_currently_behind_market_on_both_scores"])
        self.assertTrue(r["primary_shortlist_veto"])
        self.assertEqual(r["comparison"]["model_home_top_count"], 24)
        self.assertEqual(r["comparison"]["market_home_top_count"], 0)
        self.assertEqual(r["comparison"]["market_correct"], 24)
        self.assertEqual(r["comparison"]["model_correct"], 0)
        self.assertFalse(r["independent_result_authentication"])

    def test_tiny_sample_not_misrepresented_as_significant(self):
        r = build(ledger([fixture(i) for i in range(19)]))
        self.assertFalse(r["primary_shortlist_veto"])
        self.assertEqual(r["reason"], "NOT_ENOUGH_DIAGNOSTIC_CASES")

    def test_when_model_beats_market_it_still_cannot_promote(self):
        r = build(ledger([fixture(i, actual=0) for i in range(24)]))
        self.assertFalse(r["primary_shortlist_veto"])
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["out_of_sample_market_superiority_proven"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_rejects_duplicate_and_lookahead(self):
        a = fixture(0)
        with self.assertRaises(ValueError):
            build(ledger([a, copy.deepcopy(a)]))
        bad = fixture(0)
        bad["forecast_utc"] = bad["kickoff_utc"]
        with self.assertRaises(ValueError):
            build(ledger([bad]))

    def test_rejects_fake_provenance_or_record_count(self):
        data = ledger([fixture(0)])
        data["production_recommendations"] = "ENABLED"
        with self.assertRaises(ValueError):
            build(data)
        data = ledger([fixture(0)])
        data["n"] = 999
        with self.assertRaises(ValueError):
            build(data)

    def test_veto_hides_market_losing_research_directions(self):
        g = build(ledger([fixture(i) for i in range(24)]))
        s = enforce_shortlist(shortlist(), g)
        self.assertEqual(s["selected_count"], 0)
        self.assertEqual(s["review_count"], 0)
        self.assertEqual(s["model_only_count"], 0)
        self.assertEqual(s["fallback_mode"], "NOT_NEEDED")
        self.assertEqual(s["competitive_suppressed_count"], 3)
        self.assertEqual(s["status"], "HOLD")
        self.assertEqual(s["production_recommendations"], "DISABLED")
        self.assertEqual(s["diagnostics"]["research_shortlisted"], 0)

    def test_missing_or_spoofed_gate_fails_closed(self):
        self.assertEqual(enforce_shortlist(shortlist(), None)["selected_count"], 0)
        forged = build(ledger([fixture(i, actual=0) for i in range(24)]))
        forged["production_recommendations"] = "ENABLED"
        self.assertEqual(enforce_shortlist(shortlist(), forged)["selected_count"], 0)

    def test_non_underperformer_remains_research_only(self):
        g = build(ledger([fixture(i, actual=0) for i in range(24)]))
        result = enforce_shortlist(shortlist(), g)
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["competitive_suppressed_count"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_real_archived_ledger_remains_honest_about_market_comparison(self):
        # Smoke test the checked-in sealed ledger, not only hand-made examples.
        path = Path(__file__).resolve().parents[2] / "evidence" / "settled.json"
        evidence = json.loads(path.read_text(encoding="utf-8"))
        r = build(evidence)
        self.assertEqual(r["paired_same_fixture_count"], len(evidence["samples"]))
        self.assertFalse(r["out_of_sample_market_superiority_proven"])
        self.assertFalse(r["betting_ev_verified"])
        if r["comparison"]:
            c = r["comparison"]
            expected_veto = (
                len(evidence["samples"]) >= 20
                and c["model_log_loss"] > c["market_log_loss"]
                and c["model_brier"] > c["market_brier"])
            self.assertEqual(r["primary_shortlist_veto"], expected_veto)
            slate = enforce_shortlist(shortlist(), r)
            self.assertEqual(slate["selected_count"], 0 if expected_veto else 1)

    def test_publish_and_static_iphone_panel(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "index.html").write_text(
                "<html><body><h2>近期賽程與賽果</h2></body></html>",
                encoding="utf-8")
            source = root / "sealed.json"
            source.write_text(json.dumps(ledger([fixture(i) for i in range(24)])))
            self.assertTrue(publish(root, source)["primary_shortlist_veto"])
            report = json.loads((root / "competitive_guard.json").read_text())
            self.assertEqual(report["schema"], SCHEMA)
            self.assertTrue(render(root)["competitive_guard_visible"])
            page = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="fk-competitive-guard"', page)
            self.assertIn("模型首選 0/24", page)
            self.assertIn("暫停突出研究首選", page)
            with self.assertRaises(ValueError):
                render(root)


if __name__ == "__main__":
    unittest.main()
