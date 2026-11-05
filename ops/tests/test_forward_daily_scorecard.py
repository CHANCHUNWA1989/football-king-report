"""Daily forward scorecard tests, all data synthetic."""
import sys
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forward_daily_scorecard import build, publish

BASE = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def row(i, y=0):
    kickoff = BASE + timedelta(days=i)
    return {"key": str(i), "league": "epl",
            "kickoff_utc": kickoff.isoformat(),
            "forecast_utc": (kickoff-timedelta(hours=2)).isoformat(),
            "market_utc": (kickoff-timedelta(hours=3)).isoformat(),
            "p": [.8, .1, .1], "m": [.1, .1, .8], "y": y,
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED"}


def evidence(rows):
    completed = max([BASE] + [datetime.fromisoformat(r["kickoff_utc"].replace("Z", "+00:00"))
                              for r in rows]) + timedelta(hours=2)
    return {"schema": "football-king-forward-research-1",
            "checked_utc": completed.isoformat(), "samples": rows, "n": len(rows),
            "results_independently_verified": False,
            "profitability_verified": False,
            "production_recommendations": "DISABLED"}


class DailyScorecardTests(unittest.TestCase):
    def test_same_settled_cases_and_correct_weights(self):
        report = build(evidence([row(0), row(1)]))
        self.assertEqual(report["settled_observations"], 2)
        self.assertEqual(report["remaining_to_target"], 998)
        self.assertEqual(report["cumulative"]["0.00"]["correct"], 2)
        self.assertEqual(report["cumulative"]["0.50"]["correct"], 2)
        self.assertEqual(report["cumulative"]["0.75"]["correct"], 0)
        self.assertEqual(report["cumulative"]["1.00"]["correct"], 0)
        self.assertEqual(len(report["daily_utc"]), 2)
        self.assertFalse(report["statistical_superiority_proven"])
        self.assertFalse(report["results_independently_verified"])

    def test_missing_settlement_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                publish(Path(d) / "missing.json", Path(d) / "site")
            self.assertFalse((Path(d) / "site" / "forward_daily_scorecard.json").exists())

    def test_hong_kong_day_boundary(self):
        late = row(0)
        late["kickoff_utc"] = BASE.replace(hour=20).isoformat()
        report = build(evidence([late]))
        self.assertEqual(report["daily_hk"][0]["date"], "2026-10-11")
        self.assertEqual(report["daily_utc"][0]["date"], "2026-10-10")
        self.assertEqual(report["daily_hk"][0]["observations"], 1)

    def test_empty_is_hold(self):
        report = build(evidence([]))
        self.assertEqual(report["status"], "HOLD")
        self.assertIsNone(report["cumulative"]["0.00"])

    def test_invalid_sealed_rows_rejected(self):
        bad = row(0)
        bad["forecast_utc"] = (BASE+timedelta(hours=1)).isoformat()
        with self.assertRaises(ValueError):
            build(evidence([bad]))

    def test_only_completed_settlement_cutoff_is_scored(self):
        for delta in (-1, 0, 119, 120):
            with self.subTest(minutes_after_kickoff=delta):
                document = evidence([row(0)])
                document["checked_utc"] = (BASE + timedelta(minutes=delta)).isoformat()
                if delta < 120:
                    with self.assertRaisesRegex(ValueError, "SETTLEMENT_NOT_MATURE"):
                        build(document)
                else:
                    self.assertEqual(build(document)["settled_observations"], 1)

    def test_completed_cutoff_uses_absolute_instant_with_offsets(self):
        document = evidence([row(0)])
        document["checked_utc"] = "2026-10-10T22:00:00+08:00"
        self.assertEqual(build(document)["settled_observations"], 1)
        document["checked_utc"] = "2026-10-10T21:59:59+08:00"
        with self.assertRaises(ValueError):
            build(document)

    def test_error_review_common_cases_and_four_comparison_directions(self):
        rows = [row(0, y=0), row(1, y=2), row(2, y=1), row(3, y=0)]
        rows[3]["m"] = [.8, .1, .1]
        review = build(evidence(rows))["error_review"]
        counts = review["summary"]
        self.assertEqual(review["sample_count"], 4)
        self.assertTrue(review["same_cases_for_model_and_market"])
        self.assertEqual(counts["observations"], 4)
        self.assertEqual(counts["model_correct"], 2)
        self.assertEqual(counts["market_correct"], 2)
        for field in ("both_correct", "both_wrong", "model_wrong_market_right", "model_right_market_wrong"):
            self.assertEqual(counts[field], 1)
        self.assertEqual(sum(d["observations"] for d in review["daily_hk"]), 4)
        self.assertEqual(review["confusion_matrix_axes"], {"rows": "actual", "columns": "predicted"})
        self.assertEqual(review["confusion_matrices"]["original_model"], [[2, 0, 0], [1, 0, 0], [1, 0, 0]])
        self.assertEqual(review["confusion_matrices"]["market_baseline"], [[1, 0, 1], [0, 0, 1], [0, 0, 1]])
        self.assertEqual(review["direction_counts"]["predicted_home_actual_draw"], 1)
        self.assertFalse(review["automatic_parameter_changes"])
        self.assertFalse(review["automatic_model_promotion"])
        self.assertFalse(review["results_independently_verified"])
        self.assertEqual(review["production_recommendations"], "DISABLED")

    def test_error_review_uses_existing_endpoint_weight_normalization(self):
        r = row(0, y=2)
        r["p"], r["m"] = [.799, .1, .1], [.1, .1, .799]
        report = build(evidence([r]))
        case = report["error_review"]["worst_model_misses"][0]
        self.assertEqual(case["model_log_loss"], report["cumulative"]["0.00"]["log_loss"])
        self.assertEqual(case["market_log_loss"], report["cumulative"]["1.00"]["log_loss"])
        self.assertEqual(case["p"], r["p"])
        self.assertEqual(case["m"], r["m"])

    def test_worst_model_misses_are_bounded_traceable_and_ranked_by_raw_loss(self):
        rows = [row(i, y=2) for i in range(12)]
        for i, r in enumerate(rows):
            probability = .01 + i * .01
            r["p"] = [.85-probability, .15, probability]
        review = build(evidence(list(reversed(rows))))["error_review"]
        worst = review["worst_model_misses"]
        self.assertEqual(len(worst), 10)
        self.assertEqual([r["key"] for r in worst], [str(i) for i in range(10)])
        for case in worst:
            original = rows[int(case["key"])]
            for field in ("key", "league", "forecast_utc", "market_utc", "kickoff_utc", "y", "p", "m"):
                self.assertEqual(case[field], original[field])
            self.assertFalse(case["model_correct"])
        self.assertFalse(review["statistical_causation_proven"])

    def test_daily_review_uses_hong_kong_dates(self):
        late = row(0, y=1)
        late["kickoff_utc"] = "2026-10-10T20:00:00Z"
        review = build(evidence([late]))["error_review"]
        self.assertEqual(review["daily_hk"][0]["date"], "2026-10-11")
        self.assertEqual(review["daily_hk"][0]["model_incorrect"], 1)

    def test_empty_review_has_no_invented_scores_or_examples(self):
        review = build(evidence([]))["error_review"]
        self.assertEqual(review["status"], "HOLD")
        self.assertEqual(review["sample_count"], 0)
        self.assertIsNone(review["summary"])
        self.assertIsNone(review["confusion_matrices"])
        self.assertEqual(review["worst_model_misses"], [])
        self.assertEqual(review["daily_hk"], [])

    def test_duplicate_rows_and_malformed_outcomes_fail_closed(self):
        a = row(0)
        with self.assertRaises(ValueError):
            build(evidence([a, copy.deepcopy(a)]))
        for value in (True, None, "0", 3):
            invalid = row(0, y=value)
            with self.subTest(outcome=value), self.assertRaises(ValueError):
                build(evidence([invalid]))
        invalid = row(0)
        invalid["p"] = [float("nan"), .2, .8]
        with self.assertRaises(ValueError):
            build(evidence([invalid]))

    def test_review_does_not_mutate_original_evidence(self):
        source = evidence([row(0, y=2), row(1, y=1)])
        before = copy.deepcopy(source)
        report = build(source)
        self.assertEqual(source, before)
        report["error_review"]["worst_model_misses"][0]["p"][0] = 0
        self.assertEqual(source, before)

    def test_publish_review_page_and_idempotent_index_link(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, site = root / "settled.json", root / "site"
            site.mkdir()
            source.write_text(json.dumps(evidence([row(0, y=2)])), encoding="utf-8")
            (site / "index.html").write_text('<html><body><p>保留既有頁面</p></body></html>', encoding="utf-8")
            publish(source, site)
            first = (site / "index.html").read_text(encoding="utf-8")
            publish(source, site)
            self.assertEqual(first, (site / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(first.count('href="daily-review.html"'), 1)
            self.assertIn("每日模擬覆盤", first)
            self.assertIn("保留既有頁面", first)
            html = (site / "daily-review.html").read_text(encoding="utf-8")
            self.assertIn("非投注", html)
            self.assertIn("未經獨立核實", html)
            self.assertIn("forward_daily_scorecard.json", html)
            self.assertIn("模型未中／市場中", html)

    def test_publish_preserves_an_existing_review_link(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, site = root / "settled.json", root / "site"
            site.mkdir()
            source.write_text(json.dumps(evidence([])), encoding="utf-8")
            existing = "<BODY><a HREF = 'daily-review.html'>每日模擬覆盤</a></BODY>"
            (site / "index.html").write_text(existing, encoding="utf-8")
            publish(source, site)
            self.assertEqual((site / "index.html").read_text(encoding="utf-8"), existing)

    def test_page_excludes_raw_keys_and_team_names_and_escapes_text(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            r = row(0, y=2)
            r["key"] = '</script><script>alert("unsafe")</script>'
            r["home"] = 'Unverified Team Name'
            document = evidence([r])
            # ISO 8601 permits a single date/time separator character.
            document["checked_utc"] = document["checked_utc"].replace('T', '<')
            source = root / "settled.json"
            source.write_text(json.dumps(document), encoding="utf-8")
            publish(source, root / "site")
            html = (root / "site/daily-review.html").read_text(encoding="utf-8")
            self.assertNotIn(r["key"], html)
            self.assertNotIn('Unverified Team Name', html)
            self.assertNotIn('<script>', html)
            self.assertIn('&lt;', html)
            self.assertFalse((root / "site/index.html").exists())

    def test_empty_page_explains_missing_data(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "settled.json"
            source.write_text(json.dumps(evidence([])), encoding="utf-8")
            publish(source, root / "site")
            html = (root / "site/daily-review.html").read_text(encoding="utf-8")
            self.assertIn("資料不足", html)
            self.assertNotIn('100%', html.split('<body>', 1)[1])


if __name__ == "__main__":
    unittest.main()
