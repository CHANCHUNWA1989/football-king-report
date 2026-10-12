"""Versioned pre-kickoff research journal: prevent retroactive cherry-picking."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forecast_decision_journal import append_version, audit, verify


def payload(fixture="f1", revision=1, direction="HOME", status="RESEARCH",
            created="2026-10-11T14:00:00Z"):
    return {
        "fixture_id": fixture, "revision": revision,
        "created_utc": created, "kickoff_utc": "2026-10-11T15:30:00Z",
        "status": status, "market": "h2h", "direction": direction,
        "reason": "Independent uncalibrated research observation",
        "research_probability": 0.52,
    }


class JournalTests(unittest.TestCase):
    def test_initial_and_reverse_direction_are_both_retained(self):
        log = []
        log.append(append_version(log, payload()))
        log.append(append_version(log, payload(revision=2, direction="AWAY",
                        created="2026-10-11T14:30:00Z")))
        info = audit(log)
        self.assertEqual(info["unique_fixtures"], 1)
        self.assertEqual(info["version_count"], 2)
        self.assertEqual(info["direction_reversals"], 1)
        self.assertEqual(info["fixture_history"][0]["initial_direction"], "HOME")
        self.assertEqual(info["fixture_history"][0]["last_pre_kickoff_direction"], "AWAY")
        self.assertFalse(info["historical_win_rate_certified"])
        self.assertEqual(info["production_recommendations"], "DISABLED")

    def test_withdrawal_is_preserved_in_last_frozen_version(self):
        log = []
        log.append(append_version(log, payload()))
        log.append(append_version(log, payload(revision=2, direction=None,
                        status="WITHDRAW", created="2026-10-11T15:00:00Z")))
        record = audit(log)["fixture_history"][0]
        self.assertTrue(record["had_withdrawal"])
        self.assertIsNone(record["last_pre_kickoff_direction"])
        self.assertFalse(record["count_as_formal_bet"])

    def test_modified_or_removed_version_breaks_the_chain(self):
        log = []
        log.append(append_version(log, payload()))
        log.append(append_version(log, payload(revision=2, direction="AWAY",
                        created="2026-10-11T14:30:00Z")))
        tampered = copy.deepcopy(log)
        tampered[0]["payload"]["direction"] = "DRAW"
        with self.assertRaisesRegex(ValueError, "TAMPERED"):
            verify(tampered)
        with self.assertRaisesRegex(ValueError, "BROKEN"):
            verify(log[1:])

    def test_duplicate_revision_and_after_kickoff_are_rejected(self):
        log = [append_version([], payload())]
        with self.assertRaisesRegex(ValueError, "APPEND_NOT_REWRITE"):
            append_version(log, payload())
        with self.assertRaisesRegex(ValueError, "NOT_A_FROZEN_PREMATCH"):
            append_version(log, payload(revision=2, created="2026-10-11T15:25:00Z"))

    def test_later_quote_cannot_be_used_to_justify_past_forecast(self):
        p = payload()
        p.update({"observed_odds": 2.15, "quote_source": "test-book",
                  "quote_captured_utc": "2026-10-11T14:05:00Z"})
        with self.assertRaisesRegex(ValueError, "QUOTE_AFTER_FORECAST"):
            append_version([], p)
        p["quote_captured_utc"] = "2026-10-11T13:58:00Z"
        self.assertEqual(verify([append_version([], p)])["f1"]["revision"], 1)

    def test_unsupported_line_and_fake_fields_rejected(self):
        p = payload()
        p["line"] = 0.25
        with self.assertRaises(ValueError):
            append_version([], p)
        p = payload()
        p["research_probability"] = True
        with self.assertRaises(ValueError):
            append_version([], p)
        p = payload()
        p["won"] = True
        with self.assertRaises(ValueError):
            append_version([], p)

    def test_multi_fixture_journal_and_missing_history(self):
        log = []
        log.append(append_version(log, payload()))
        log.append(append_version(log, payload("f2", created="2026-10-11T14:10:00Z")))
        self.assertEqual(audit(log)["unique_fixtures"], 2)
        self.assertEqual(audit([])["status"], "HOLD")
        p = payload("f3", revision=2, created="2026-10-11T14:30:00Z")
        with self.assertRaisesRegex(ValueError, "APPEND_NOT_REWRITE"):
            append_version(log, p)


if __name__ == "__main__":
    unittest.main()
