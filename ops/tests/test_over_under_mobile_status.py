"""Fail-closed iPhone AH/OU coverage and research-only status tests."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from over_under_mobile_status import market_disclosure, publish


def market(**patch):
    data = {
        "schema": "football-king-market-consensus-v1",
        "status": "RESEARCH_ONLY",
        "market": "h2h",
        "requested_markets": ["h2h"],
        "missing_markets": ["spreads", "totals"],
        "handicap_and_totals_verified": False,
        "as_of_utc": "2026-11-02T02:02:25+00:00",
        "event_count": 2,
        "events": [{"id": "a"}, {"id": "b"}],
    }
    data.update(patch)
    return data


def setup_site(p, *, candidates=0, production="DISABLED", status="NO_VERIFIED_MARKET_INPUT"):
    (p / "index.html").write_text(
        "<html><body><main>Hi</main></body></html>", encoding="utf-8")
    (p / "over_under_25.json").write_text(json.dumps({
        "candidate_count": candidates,
        "input_status": status,
        "generated_at_utc": "2026-11-02T02:03:00Z",
        "production_recommendations": production,
    }), encoding="utf-8")


class MobileStatusTests(unittest.TestCase):
    def test_visible_idempotent_and_holds_without_market(self):
        with TemporaryDirectory() as d:
            p = Path(d)
            setup_site(p)
            publish(p)
            publish(p)
            page = (p / "index.html").read_text(encoding="utf-8")
            self.assertEqual(page.count('id="fk-ou25"'), 1)
            self.assertIn("over_under_25.json", page)
            self.assertIn("正式投注推薦：停用", page)
            self.assertIn("讓球盤及入球大細盤均未獲核實", page)

    def test_real_consensus_count_is_not_misrepresented_as_asian_quotes(self):
        with TemporaryDirectory() as d:
            p = Path(d)
            setup_site(p)
            path = p / "market.json"
            path.write_text(json.dumps(market()), encoding="utf-8")
            publish(p, path, now_utc=datetime(2026, 11, 2, 4, tzinfo=timezone.utc))
            publish(p, path, now_utc=datetime(2026, 11, 2, 4, tzinfo=timezone.utc))
            page = (p / "index.html").read_text(encoding="utf-8")
            self.assertEqual(page.count('id="fk-ou25"'), 1)
            self.assertIn("2場1X2去水共識概率", page)
            self.assertIn("2026-11-02 02:02 UTC", page)
            self.assertIn("亞洲讓球盤及入球大細盤均缺少可核實盤口", page)
            self.assertIn("不能計算可執行正EV", page)

    def test_malformed_or_false_coverage_remains_unverified(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "market.json"
            for altered in (
                {"event_count": 3},
                {"status": "READY"},
                {"missing_markets": []},
                {"handicap_and_totals_verified": True},
                {"requested_markets": ["h2h", "totals"]},
                {"as_of_utc": "bad"},
                {"as_of_utc": "2026-11-02T02:02:25"},
                {"event_count": True},
            ):
                with self.subTest(altered=altered):
                    p.write_text(json.dumps(market(**altered)), encoding="utf-8")
                    self.assertEqual(market_disclosure(
                        p, now_utc=datetime(2026, 11, 2, 4, tzinfo=timezone.utc)),
                                     "市場快照缺失或無法核對；讓球盤及入球大細盤均未獲核實。")

    def test_stale_snapshot_is_quarantined_and_not_displayed_as_current(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            setup_site(root)
            path = root / "market.json"
            path.write_text(json.dumps(market()), encoding="utf-8")
            cutoff = datetime(2026, 11, 2, 12, 2, 25, tzinfo=timezone.utc)
            current = market_disclosure(path, now_utc=cutoff)
            self.assertIn("2場1X2去水共識概率", current)
            expired = market_disclosure(path, now_utc=cutoff + timedelta(seconds=1))
            self.assertIn("1X2市場快照已過期", expired)
            self.assertNotIn("2場1X2去水共識概率", expired)
            self.assertIn("不可當成目前盤口", expired)
            publish(root, path, now_utc=cutoff + timedelta(days=2))
            page = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("1X2市場快照已過期", page)
            self.assertNotIn("2場1X2去水共識概率", page)
            self.assertIn("正式投注推薦：停用", page)

    def test_future_snapshot_and_invalid_validation_clock_fail_closed(self):
        with TemporaryDirectory() as d:
            path = Path(d) / "market.json"
            path.write_text(json.dumps(market()), encoding="utf-8")
            for now in (
                datetime(2026, 11, 2, 2, 2, 24, tzinfo=timezone.utc),
                datetime(2026, 11, 2, 3),
                "2026-11-02T03:00:00Z",
            ):
                with self.subTest(now=now):
                    self.assertEqual(
                        market_disclosure(path, now_utc=now),
                        "市場快照缺失或無法核對；讓球盤及入球大細盤均未獲核實。"
                    )

    def test_rejects_fake_formal_status_and_unevidenced_candidates(self):
        with TemporaryDirectory() as d:
            p = Path(d)
            setup_site(p, production="ENABLED")
            with self.assertRaises(ValueError):
                publish(p)
            setup_site(p, candidates=3)
            with self.assertRaises(ValueError):
                publish(p)

    def test_untrusted_status_is_html_escaped(self):
        with TemporaryDirectory() as d:
            p = Path(d)
            setup_site(p, status="<script>alert(1)</script>")
            publish(p)
            page = (p / "index.html").read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;", page)
            self.assertNotIn("<script>", page)


if __name__ == "__main__":
    unittest.main()
