"""Synthetic KPL data only; no real match results or verified external feeds."""
import copy
import unittest
from research.kpl_v7_bp_evidence import audit_bp_snapshot

NOW = "2026-11-03T12:00:30Z"


def row(n=1):
    return {"event_id": "synthetic-kpl-001", "game_number": n,
            "team_ids": ["WB", "EDGM"],
            "side_by_team": {"WB": "blue", "EDGM": "red"},
            "picks_by_team": {"WB": [f"w{n}-{x}" for x in range(5)],
                              "EDGM": [f"e{n}-{x}" for x in range(5)]},
            "bans_by_team": {"WB": [f"bw{n}"], "EDGM": [f"be{n}"]},
            "source": "synthetic-source", "source_authenticated": True,
            "bp_complete": True, "published_at": "2026-11-03T11:59:00Z",
            "observed_at": "2026-11-03T12:00:00Z"}


class BPTests(unittest.TestCase):
    def test_valid_fresh_g1(self):
        result = audit_bp_snapshot(row(), [], now_utc=NOW)
        self.assertEqual(result["status"], "VALIDATED_RESEARCH_INPUT")
        self.assertFalse(result["live_execution_allowed"])

    def test_own_hero_reuse_fails(self):
        prev = row()
        current = row(2)
        current["picks_by_team"]["WB"][0] = prev["picks_by_team"]["WB"][0]
        self.assertIn("OWN_HERO_REUSE", audit_bp_snapshot(current, [prev], now_utc=NOW)["reasons"])

    def test_peak_duel_allows_reuse(self):
        prior = [row(n) for n in range(1, 7)]
        current = row(7)
        current["picks_by_team"] = copy.deepcopy(prior[0]["picks_by_team"])
        self.assertEqual(audit_bp_snapshot(current, prior, now_utc=NOW)["status"], "VALIDATED_RESEARCH_INPUT")

    def test_missing_previous_game_fails(self):
        self.assertIn("HISTORY_INCOMPLETE_OR_UNORDERED",
                      audit_bp_snapshot(row(3), [row(1)], now_utc=NOW)["reasons"])

    def test_source_unverified_fails(self):
        current = row()
        current["source_authenticated"] = False
        self.assertIn("SOURCE_AUTHENTICATION_MISSING",
                      audit_bp_snapshot(current, [], now_utc=NOW)["reasons"])

    def test_stale_fails(self):
        self.assertIn("STALE_SOURCE",
                      audit_bp_snapshot(row(), [], now_utc="2026-11-03T12:05:00Z")["reasons"])

    def test_duplicate_pick_fails(self):
        current = row()
        current["picks_by_team"]["EDGM"][0] = current["picks_by_team"]["WB"][0]
        self.assertIn("CROSS_TEAM_PICK_DUPLICATE",
                      audit_bp_snapshot(current, [], now_utc=NOW)["reasons"])

    def test_bad_history_attestation_fails(self):
        prev = row()
        prev["source_authenticated"] = False
        self.assertIn("UNVERIFIED_OR_INVALID_HISTORY",
                      audit_bp_snapshot(row(2), [prev], now_utc=NOW)["reasons"])

    def test_invalid_clock_fails(self):
        current = row()
        current["observed_at"] = "2026-11-03T12:00:00"
        self.assertIn("INVALID_SOURCE_CLOCK",
                      audit_bp_snapshot(current, [], now_utc=NOW)["reasons"])

    def test_invalid_side_value_fails_closed(self):
        current = row()
        current["side_by_team"]["WB"] = ["blue"]
        self.assertIn("INVALID_SIDES",
                      audit_bp_snapshot(current, [], now_utc=NOW)["reasons"])

    def test_bad_ban_conflict_fails(self):
        current = row()
        current["bans_by_team"]["WB"][0] = current["picks_by_team"]["EDGM"][0]
        self.assertIn("PICK_BAN_CONFLICT",
                      audit_bp_snapshot(current, [], now_utc=NOW)["reasons"])


if __name__ == "__main__":
    unittest.main()
