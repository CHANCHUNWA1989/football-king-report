import unittest
import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_live_snapshot_commitment import envelope, NOW
from live_snapshot_commitment import commitment
from vnext_integrated_replay import replay
from vnext_live_evidence_cut import audit_cut, cut_digest

def stamp(n):
    return datetime.fromtimestamp(n, timezone.utc).isoformat()

def sample():
    e = envelope()
    a = e["a"]
    fid = a["fixture_id"]
    base = dict(event_id=fid, source="stats", upstream_updated_utc=stamp(NOW-4),
                captured_utc=stamp(NOW-2))
    s = dict(event_id=fid, kickoff_utc=e["model"]["kickoff_utc"], decision_utc=stamp(NOW),
             score=dict(base, source=a["origin"], upstream_updated_utc=stamp(a["observed"]),
                        captured_utc=stamp(a["received"]), home_goals=a["home"],
                        away_goals=a["away"], minute=a["minute"], phase=a["phase"],
                        red_home=a["red_home"], red_away=a["red_away"],
                        last_material_event_utc=stamp(NOW-120)),
             stats=dict(base, home_xg=.2, away_xg=.9),
             quote=dict(base, source="odds", market="totals", selection="over",
                        line=2.25, decimal_price=1.91, bookmaker="synthetic",
                        in_play=True, scope="FULL_MATCH_REGULATION"))
    return e,s

class EvidenceCutTests(unittest.TestCase):
    def test_bound_cut_is_never_certified(self):
        e,s=sample()
        o=audit_cut(e,s,cut_digest(e,s),NOW)
        self.assertEqual(o["cut_status"],"STRUCTURAL_RESEARCH_ONLY")
        self.assertEqual(o["status"],"HOLD")
        self.assertEqual(o["production_recommendations"],"DISABLED")
        self.assertIsNone(o["actual_xg"])
        self.assertIsNone(o["model_edge"])
        self.assertFalse(o["positive_ev_verified"])

    def test_bound_line_uses_same_full_time_distribution_as_1x2(self):
        e, s = sample()
        expected_1x2 = replay(e, commitment(e), NOW)["probabilities_1x2"]
        for market, selection, line in (
            ("totals", "over", 1.75),
            ("totals", "over", 2.25),
            ("asian_handicap", "away", -0.75),
        ):
            with self.subTest(market=market, line=line):
                s["quote"].update(market=market, selection=selection, line=line)
                output = audit_cut(e, s, cut_digest(e, s), NOW)
                self.assertEqual(output["status"], "HOLD")
                self.assertFalse(output["actual_quote_verified"])
                diagnostic = output["research_diagnostics"]
                self.assertEqual(diagnostic["probabilities_1x2"], expected_1x2)
                distribution, = diagnostic["diagnostic_distributions"]
                self.assertEqual((distribution["market"], distribution["side"], distribution["line"]),
                                 (market, selection.upper(), line))
                probabilities = distribution["outcome_probabilities"]
                self.assertAlmostEqual(sum(probabilities.values()), 1)
                if line == 1.75:
                    self.assertAlmostEqual(probabilities["FULL_WIN"] + probabilities["HALF_WIN"], 1)
                    self.assertGreater(probabilities["HALF_WIN"], 0)
                if line == 2.25:
                    self.assertGreater(probabilities["HALF_LOSS"], 0)
                    self.assertEqual(probabilities["FULL_LOSS"], 0)

    def test_bound_price_does_not_change_model_distribution(self):
        e, s = sample()
        before = audit_cut(e, s, cut_digest(e, s), NOW)
        s["quote"]["decimal_price"] = 2.1
        after = audit_cut(e, s, cut_digest(e, s), NOW)
        self.assertNotEqual(before["cut_sha256_unattested"], after["cut_sha256_unattested"])
        self.assertEqual(before["research_diagnostics"], after["research_diagnostics"])
        self.assertIsNone(after["model_edge"])

    def test_mutated_quote_rejected(self):
        e,s=sample()
        d=cut_digest(e,s)
        s["quote"]["decimal_price"]=2.1
        output = audit_cut(e, s, d, NOW)
        self.assertEqual(output["reason"], "CUT_COMMITMENT_MISMATCH")
        self.assertNotIn("research_diagnostics", output)
    def test_cross_cut_mismatch(self):
        for k,v in (("home_goals",1),("minute",51),("red_home",1),("phase","FIRST_HALF")):
            with self.subTest(k=k):
                e,s=sample()
                s["score"][k]=v
                self.assertEqual(audit_cut(e,s,cut_digest(e,s),NOW)["reason"],"CROSS_CUT_STATE_MISMATCH")
    def test_bad_scope_stale_quote_missing_xg_and_near_quarter(self):
        for k,v in (("scope","REMAINING_ONLY"),("upstream_updated_utc",stamp(NOW-91)),("line",2.25000000001)):
            with self.subTest(k=k):
                e,s=sample()
                s["quote"][k]=v
                o=audit_cut(e,s,cut_digest(e,s),NOW)
                self.assertNotIn("cut_status",o)
                self.assertNotIn("research_diagnostics", o)
                self.assertEqual(o["status"],"HOLD")
        e,s=sample()
        del s["stats"]["home_xg"]
        self.assertNotIn("cut_status",audit_cut(e,s,cut_digest(e,s),NOW))
    def test_unbound_score_source(self):
        e,s=sample()
        s["score"]["source"]="other"
        self.assertEqual(audit_cut(e,s,cut_digest(e,s),NOW)["reason"],"SCORE_RECORD_NOT_BOUND")
    def test_event_older_than_changed_state(self):
        e,s=sample()
        for k in ("previous_a","previous_b"):
            e[k]["away"]=1
        self.assertEqual(audit_cut(e,s,cut_digest(e,s),NOW)["reason"],"EVENT_TIME_CONFLICT")

    def test_material_event_must_precede_both_observations(self):
        # Bind to the later source: the old single-score-clock guard would
        # accept an event after the other claimed observation.
        for early, late in (("a", "b"), ("b", "a")):
            with self.subTest(early=early):
                e, s = sample()
                e[early]["observed"] = NOW-10
                e[late]["observed"] = NOW-8
                for source in ("a", "b"):
                    e["previous_"+source]["away"] = 1
                s["score"].update(source=e[late]["origin"],
                                  upstream_updated_utc=stamp(e[late]["observed"]),
                                  captured_utc=stamp(e[late]["received"]))
                s["score"]["last_material_event_utc"] = stamp(NOW-9)
                out = audit_cut(e,s,cut_digest(e,s),NOW)
                self.assertEqual(out["reason"],"EVENT_TIME_CONFLICT")
                self.assertNotIn("research_diagnostics",out)
                self.assertEqual(out["production_recommendations"],"DISABLED")
                self.assertFalse(out["positive_ev_verified"])
                # Equality is structurally admissible, not authentication.
                s["score"]["last_material_event_utc"] = stamp(NOW-10)
                out = audit_cut(e,s,cut_digest(e,s),NOW)
                self.assertEqual(out["cut_status"],"STRUCTURAL_RESEARCH_ONLY")
                self.assertFalse(out["source_authenticated"])
                self.assertIsNone(out["model_edge"])
