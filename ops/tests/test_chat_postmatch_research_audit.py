"""Retrospective conversation picks are NEVER the sealed forecast ledger."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_postmatch_research_audit import audit, publish


def pick(fid, market, side, line, score, *, prior=None, price=None):
    def choice(direction):
        row = {"market": market, "direction": direction, "line": line}
        if price is not None:
            row["unverified_reference_price"] = price
        return row
    versions = [choice(prior), choice(side)] if prior else [choice(side)]
    return {
        "fixture_ref": fid,
        "source_evidence": "POSTMATCH_CHAT_RECAP_UNVERIFIED",
        "result_source_url": "https://example.org/matches/" + fid,
        "score_ft": score,
        "versions": versions,
    }


def four_picks():
    return [
        pick("frankfurt-hamburg-20261101", "totals", "UNDER", 3.5, [3, 1],
             prior="OVER", price=1.84),
        pick("braga-famalicao-20261101", "asian_handicap", "AWAY", .75, [3, 0],
             price=1.93),
        pick("union-koln-20261101", "totals", "OVER", 2.75, [1, 1], price=2.01),
        pick("liverpool-arsenal-20261101", "totals", "UNDER", 2.5, [0, 1],
             price=2.02),
    ]


class ChatPostmatchAuditTests(unittest.TestCase):
    def test_four_unsealed_picks_grade_last_claim_only(self):
        result = audit(four_picks())
        self.assertEqual(result["case_count"], 4)
        self.assertEqual(result["changed_direction_cases"], 1)
        self.assertEqual(result["total_claimed_versions"], 5)
        self.assertEqual(result["last_version_grades"],
                         {"FULL_WIN": 1, "FULL_LOSS": 3,
                          "HALF_WIN": 0, "PUSH": 0, "HALF_LOSS": 0})
        first = result["cases"][0]
        self.assertEqual(first["last_claimed_direction"], "UNDER")
        self.assertEqual(first["grade_if_reported_score_is_correct"], "FULL_LOSS")
        self.assertEqual(first["directions_reported_in_order"], ["OVER", "UNDER"])
        self.assertFalse(first["version_order_independently_authenticated"])
        self.assertFalse(result["sealed_prematch_forecasts"])
        self.assertFalse(result["independently_verified_results"])
        self.assertFalse(result["executable_prices_authenticated"])
        self.assertEqual(result["certified_forward_samples"], 0)
        self.assertEqual(result["formal_bet_count"], 0)
        self.assertIsNone(result["roi"])
        self.assertIsNone(result["ev"])
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertNotIn("1.84", json.dumps(result))

    def test_quarter_handicap_and_total_grades_use_five_grade_semantics(self):
        rows = [
            pick("a", "asian_handicap", "HOME", -.75, [1, 0]),
            pick("b", "asian_handicap", "AWAY", 1.25, [1, 0]),
            pick("c", "totals", "UNDER", 2.25, [1, 1]),
            pick("d", "totals", "OVER", 2.75, [2, 1]),
            pick("e", "totals", "UNDER", 2.0, [1, 1]),
        ]
        got = audit(rows)["cases"]
        self.assertEqual([x["grade_if_reported_score_is_correct"] for x in got],
                         ["FULL_WIN", "HALF_WIN", "HALF_WIN", "HALF_WIN", "PUSH"])

    def test_unverified_reference_price_does_not_certify_bet(self):
        case = pick("one", "totals", "UNDER", 3.5, [2, 1], price=1.84)
        result = audit([case])
        self.assertEqual(result["unverified_reference_price_claims"], 1)
        self.assertFalse(result["executable_prices_authenticated"])
        self.assertFalse(result["can_enter_formal_settlement_ledger"])

    def test_reject_lookahead_backfill_as_if_it_were_a_seal(self):
        case = pick("a", "totals", "UNDER", 3.5, [1, 1])
        for field, value in (("created_utc", "2026-11-01T11:00:00Z"),
                             ("certified", True), ("model_probability", .8),
                             ("quote_captured_utc", "2026-11-01T10:00:00Z")):
            bad = copy.deepcopy(case)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit([bad])

    def test_bad_score_line_market_and_versions_fail_closed(self):
        for bad in (
                pick("x", "totals", "OVER", 2.31, [1, 2]),
                pick("x", "totals", "OVER", 2.5, [-1, 2]),
                pick("x", "totals", "AWAY", 2.5, [2, 2]),
                pick("x", "asian_handicap", "UNDER", .75, [2, 2]),
                pick("x", "totals", "OVER", 2.5, [2, True]),
                pick("x", "totals", "OVER", float("nan"), [2, 1]),
                pick("x", "totals", "OVER", 2.5, [1, 2], price=True)):
            with self.subTest(bad=repr(bad)), self.assertRaises(ValueError):
                audit([bad])
        case = pick("x", "totals", "OVER", 2.5, [1, 2])
        case["versions"].append(case["versions"][-1])
        with self.assertRaises(ValueError):
            audit([case])  # identical revisions are not a new recorded change

    def test_bad_url_duplicate_and_untrusted_source_fail_closed(self):
        one = pick("x", "totals", "UNDER", 3.5, [1, 1])
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            audit([one, copy.deepcopy(one)])
        for field, value in (("result_source_url", "http://example.org"),
                             ("result_source_url", "https://x:secret@example.org/x"),
                             ("source_evidence", "SEALED_PREMATCH")):
            item = copy.deepcopy(one)
            item[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit([item])
        with self.assertRaises(ValueError):
            audit([{"fixture_ref": "a"}])

    def test_output_published_as_research_only_without_mutating_inputs(self):
        items = four_picks()
        original = copy.deepcopy(items)
        with tempfile.TemporaryDirectory() as temp:
            inp, out = Path(temp) / "user_recap.json", Path(temp) / "review.json"
            inp.write_text(json.dumps(items), encoding="utf-8")
            report = publish(inp, out)
            self.assertEqual(report["case_count"], 4)
            self.assertEqual(json.loads(out.read_text())["status"], "RESEARCH_ONLY")
            self.assertEqual(json.loads(inp.read_text()), original)
            self.assertIsNone(report["roi"])
            self.assertFalse(report["can_enter_formal_settlement_ledger"])


if __name__ == "__main__":
    unittest.main()
