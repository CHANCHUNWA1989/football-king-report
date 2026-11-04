"""Offline synthetic two-provider score, red-card and VAR regression tests."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_event_consensus import reconcile

KO = "2026-11-03T20:00:00Z"
DECISION = "2026-11-03T20:49:00Z"
FIXTURE = {
    "fixture_id": "ucl-research-001", "gender": "men", "league": "ucl",
    "home_id": "home-001", "away_id": "away-001", "kickoff_utc": KO,
    "expected_identity_sealed_utc": "2026-11-03T19:00:00Z",
    "provider_event_ids": {"fotmob": "111", "skysports": "222"},
    "provider_event_urls": {
        "fotmob": "https://www.fotmob.com/en-GB/matches/example/111",
        "skysports": "https://www.skysports.com/football/example/live/222",
    },
    "source_groups_by_provider": {"fotmob": "origin-a", "skysports": "origin-b"},
}


def ev(key="g1", kind="GOAL", side="HOME", minute=30, rev=1,
       state="CONFIRMED", updated="2026-11-03T20:35:00Z",
       received="2026-11-03T20:35:01Z"):
    return {
        "event_key": key, "type": kind, "side": side, "minute": minute,
        "revision": rev, "state": state, "source_updated_utc": updated,
        "received_utc": received,
    }


def feed(provider, *, goals=1, events=None):
    return {
        "provider": provider, "source_event_id": FIXTURE["provider_event_ids"][provider],
        "gender": "men", "league": "ucl", "home_id": "home-001",
        "away_id": "away-001", "kickoff_utc": KO,
        "source_url": FIXTURE["provider_event_urls"][provider],
        "source_group": FIXTURE["source_groups_by_provider"][provider],
        "match_status": "FIRST_HALF", "score_home": goals, "score_away": 0,
        "source_updated_utc": "2026-11-03T20:48:00Z",
        "captured_utc": "2026-11-03T20:48:01Z",
        "received_utc": "2026-11-03T20:48:02Z",
        "available_utc": "2026-11-03T20:48:03Z",
        "events_complete_since_kickoff": True,
        "event_revisions": [ev()] if events is None else events,
    }


def feeds(goals=1, events=None):
    return [feed("fotmob", goals=goals, events=events),
            feed("skysports", goals=goals, events=events)]


def check(rows=None, fixture=None, decision=DECISION):
    return reconcile(FIXTURE if fixture is None else fixture,
                     feeds() if rows is None else rows, decision_utc=decision)


def overturn():
    return [
        ev(),
        ev(rev=2, state="UNDER_REVIEW", updated="2026-11-03T20:40:00Z",
           received="2026-11-03T20:40:01Z"),
        ev(rev=3, state="OVERTURNED", updated="2026-11-03T20:41:00Z",
           received="2026-11-03T20:41:01Z"),
    ]


class ConsensusTests(unittest.TestCase):
    def test_agreement_never_verifies_live_source_or_betting(self):
        r = check()
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual((r["score_home"], r["score_away"]), (1, 0))
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(len(r["evidence_input_sha256"]), 64)
        for field in ("model_scoring_eligible", "source_authenticated",
                      "source_independence_verified", "event_truth_verified",
                      "settlement_certified", "positive_ev_verified"):
            self.assertFalse(r[field])

    def test_red_card_two_source_confirmation_is_still_research(self):
        rows = feeds()
        for row in rows:
            row["event_revisions"].append(ev(key="r1", kind="RED_CARD", side="AWAY", minute=34))
        r = check(rows)
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["active_red_cards"], {"HOME": 0, "AWAY": 1})

    def test_unmatched_red_card_always_holds(self):
        rows = feeds()
        rows[0]["event_revisions"].append(ev(key="r1", kind="RED_CARD", side="AWAY", minute=34))
        self.assertEqual(check(rows)["reason"], "CROSS_SOURCE_EVENT_OR_VAR_CONFLICT")

    def test_var_overturn_goal_changes_confirmed_score(self):
        r = check(feeds(goals=0, events=overturn()))
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual((r["score_home"], r["var_overturned_count"]), (0, 1))

    def test_var_under_review_holds(self):
        rows = feeds(events=overturn()[:2])
        self.assertEqual(check(rows)["reason"], "VAR_PENDING_NOT_SETTLED")

    def test_var_revisions_disagree_holds(self):
        rows = feeds(goals=0, events=overturn())
        rows[1]["event_revisions"][1]["state"] = "CONFIRMED"
        self.assertEqual(check(rows)["status"], "HOLD")

    def test_var_revision_gap_or_duplicate_holds(self):
        for bad_rev in (1, 3):
            with self.subTest(rev=bad_rev):
                rows = feeds()
                for row in rows:
                    row["event_revisions"].append(ev(rev=bad_rev,
                        state="UNDER_REVIEW", updated="2026-11-03T20:40:00Z",
                        received="2026-11-03T20:40:01Z"))
                self.assertEqual(check(rows)["reason"], "EVENT_REVISION_GAP_OR_DUPLICATE")

    def test_var_overturn_without_review_rejected(self):
        rows = feeds(goals=0)
        for row in rows:
            row["event_revisions"].append(ev(rev=2, state="OVERTURNED",
                updated="2026-11-03T20:40:00Z",
                received="2026-11-03T20:40:01Z"))
        self.assertEqual(check(rows)["reason"], "INVALID_VAR_TRANSITION")

    def test_red_card_overturn_no_active_red(self):
        history = [
            ev(key="r1", kind="RED_CARD", side="AWAY", minute=34),
            ev(key="r1", kind="RED_CARD", side="AWAY", minute=34, rev=2,
               state="UNDER_REVIEW", updated="2026-11-03T20:40:00Z",
               received="2026-11-03T20:40:01Z"),
            ev(key="r1", kind="RED_CARD", side="AWAY", minute=34, rev=3,
               state="OVERTURNED", updated="2026-11-03T20:41:00Z",
               received="2026-11-03T20:41:01Z"),
        ]
        r = check(feeds(goals=0, events=history))
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["active_red_cards"]["AWAY"], 0)

    def test_score_conflict_blocks_events(self):
        rows = feeds()
        rows[1]["score_home"] = 2
        self.assertTrue(check(rows)["reason"].startswith("SCORE_GATE:"))

    def test_score_not_supported_by_full_history_holds(self):
        self.assertEqual(check(feeds(events=[]))["reason"], "SCORE_EVENT_HISTORY_CONFLICT")

    def test_different_event_minute_holds(self):
        rows = feeds()
        rows[1]["event_revisions"][0]["minute"] = 31
        self.assertEqual(check(rows)["reason"], "CROSS_SOURCE_EVENT_OR_VAR_CONFLICT")

    def test_missing_full_history_declaration_holds(self):
        rows = feeds()
        rows[0]["events_complete_since_kickoff"] = False
        self.assertEqual(check(rows)["reason"], "INCOMPLETE_EVENT_HISTORY")

    def test_late_received_event_cannot_enter_old_prediction(self):
        rows = feeds()
        rows[0]["event_revisions"][0]["received_utc"] = "2026-11-03T20:52:00Z"
        self.assertEqual(check(rows)["reason"], "EVENT_TIME_NOT_AVAILABLE")

    def test_late_received_feed_is_not_available_at_decision(self):
        rows = feeds()
        for row in rows:
            row["received_utc"] = "2026-11-03T20:52:00Z"
            row["available_utc"] = "2026-11-03T20:52:01Z"
        self.assertEqual(check(rows)["status"], "HOLD")

    def test_shared_upstream_not_counted_as_independent(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture["source_groups_by_provider"]["skysports"] = "origin-a"
        self.assertEqual(check(fixture=fixture)["reason"],
                         "SOURCE_GROUPS_NOT_DISTINCT_OR_PREDECLARED")

    def test_source_group_backfill_does_not_pass(self):
        rows = feeds()
        rows[1]["source_group"] = "invented"
        self.assertEqual(check(rows)["reason"], "SOURCE_GROUP_MISMATCH")

    def test_wrong_fixture_or_duplicate_provider_holds(self):
        for field, value in (("home_id", "wrong-team"), ("provider", "fotmob")):
            with self.subTest(field=field):
                rows = feeds()
                rows[1][field] = value
                self.assertTrue(check(rows)["reason"].startswith("SCORE_GATE:"))

    def test_malformed_revisions_fail_closed(self):
        for update in ({"minute": True}, {"revision": 0}, {"state": "FAKE"}):
            with self.subTest(update=update):
                rows = feeds()
                for row in rows:
                    row["event_revisions"][0].update(update)
                self.assertEqual(check(rows)["reason"], "INVALID_EVENT_FIELDS")

    def test_event_revision_time_rollback_fails(self):
        rows = feeds(goals=0, events=overturn())
        for row in rows:
            row["event_revisions"][2]["received_utc"] = "2026-11-03T20:39:59Z"
        self.assertEqual(check(rows)["reason"], "EVENT_REVISION_TIME_ROLLBACK")

    def test_0_0_no_goal_events_passes_research_only(self):
        r = check(feeds(goals=0, events=[]))
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["event_count"], 0)


if __name__ == "__main__":
    unittest.main()
