"""Offline synthetic-only tests. No actual Tencent calls, rights or game evidence."""
import copy
import unittest
from research.kpl_v9_offline_source_ingest import canonical_digest, inspect_offline_battle

NOW = "2026-11-03T12:05:30Z"


def fixture(game=1):
    payload = {
        "league_id": "synthetic-2026", "match_id": "synthetic-match-001",
        "battle_id": f"synthetic-battle-{game}", "battle_seq": game,
        "camp1": {"team_id": "blue-team" if game % 2 else "red-team"},
        "camp2": {"team_id": "red-team" if game % 2 else "blue-team"},
        "bp_list": []}
    for index in range(10):
        payload["bp_list"].append({"camp": 1 if index < 5 else 2,
                                    "is_ban_or_pick": 0,
                                    "hero_id": f"ban{game}-{index}"})
    for index in range(10):
        payload["bp_list"].append({"camp": 1 if index < 5 else 2,
                                    "is_ban_or_pick": 1,
                                    "hero_id": f"pick{game}-{index}"})
    match_index = {
        "league_id": payload["league_id"], "match_id": payload["match_id"],
        "team_ids": ["blue-team", "red-team"],
        "battles": [{"battle_seq": n, "battle_id": f"synthetic-battle-{n}",
                     "blue_team_id": "blue-team" if n % 2 else "red-team",
                     "red_team_id": "red-team" if n % 2 else "blue-team"}
                    for n in range(1, game + 1)]}
    provenance = {"source_url": "https://prod.comp.smoba.qq.com/leaguesite/battle/open?battle_id="
                 + payload["battle_id"],
                  "sha256": canonical_digest(payload),
                  "transport": "OFFLINE_SUPPLIED_SNAPSHOT",
                  "published_at": "2026-11-03T12:04:00Z",
                  "observed_at": "2026-11-03T12:05:00Z",
                  "source_authenticated": True, "license_granted": True}
    return payload, match_index, provenance


def inspect(p, i, v, *, previous_games=None, now_utc=NOW):
    return inspect_offline_battle(p, i, v, now_utc=now_utc,
                                  previous_games=previous_games)


class TestKPLV9OfflineSourceIntake(unittest.TestCase):
    def test_structural_pass_still_hold(self):
        p, i, v = fixture()
        r = inspect(p, i, v)
        self.assertTrue(r["structural_validation_passed"])
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["provider_data_usage_rights_verified"])
        self.assertFalse(r["independent_match_authentication_verified"])
        self.assertFalse(r["normalized_snapshot"]["source_authenticated"])
        self.assertEqual(r["network_requests_made"], 0)

    def test_sha_mismatch(self):
        p, i, v = fixture()
        p["bp_list"][0]["hero_id"] = "mutated"
        self.assertIn("PAYLOAD_DIGEST_MISMATCH", inspect(p, i, v)["reasons"])

    def test_false_official_subdomain(self):
        p, i, v = fixture()
        v["source_url"] = "https://prod.comp.smoba.qq.com.attacker.invalid/leaguesite/battle/open?battle_id=" + p["battle_id"]
        self.assertIn("SOURCE_URL_NOT_EXACT_OFFICIAL_BATTLE_ROUTE", inspect(p, i, v)["reasons"])

    def test_url_query_attack(self):
        p, i, v = fixture()
        v["source_url"] += "&battle_id=other"
        self.assertIn("SOURCE_URL_NOT_EXACT_OFFICIAL_BATTLE_ROUTE", inspect(p, i, v)["reasons"])

    def test_battle_id_mismatch(self):
        p, i, v = fixture()
        i["battles"][0]["battle_id"] = "different"
        self.assertIn("BATTLE_MATCH_IDENTITY_MISMATCH", inspect(p, i, v)["reasons"])

    def test_swapped_side_identity(self):
        p, i, v = fixture()
        p["camp1"]["team_id"] = "red-team"
        p["camp2"]["team_id"] = "blue-team"
        v["sha256"] = canonical_digest(p)
        self.assertIn("BATTLE_MATCH_IDENTITY_MISMATCH", inspect(p, i, v)["reasons"])

    def test_stale_capture(self):
        p, i, v = fixture()
        self.assertIn("STALE_CAPTURE", inspect(p, i, v, now_utc="2026-11-03T12:12:00Z")["reasons"])

    def test_future_capture(self):
        p, i, v = fixture()
        v["observed_at"] = "2026-11-03T12:06:00Z"
        self.assertIn("FUTURE_CAPTURE", inspect(p, i, v)["reasons"])

    def test_timezone_missing(self):
        p, i, v = fixture()
        v["observed_at"] = "2026-11-03T12:05:00"
        self.assertIn("INVALID_PROVENANCE_CLOCK", inspect(p, i, v)["reasons"])

    def test_incomplete_bp(self):
        p, i, v = fixture()
        p["bp_list"].pop()
        v["sha256"] = canonical_digest(p)
        self.assertIn("INCOMPLETE_OR_INVALID_BP", inspect(p, i, v)["reasons"])

    def test_duplicate_hero(self):
        p, i, v = fixture()
        p["bp_list"][15]["hero_id"] = p["bp_list"][10]["hero_id"]
        v["sha256"] = canonical_digest(p)
        self.assertIn("INCOMPLETE_OR_INVALID_BP", inspect(p, i, v)["reasons"])

    def test_prior_history_missing(self):
        p, i, v = fixture(2)
        self.assertIn("INCOMPLETE_PRIOR_GAMES", inspect(p, i, v)["reasons"])

    def test_prior_history_swapped_sides_allowed(self):
        p1, i1, v1 = fixture(1)
        g1 = inspect(p1, i1, v1)["normalized_snapshot"]
        p2, i2, v2 = fixture(2)
        g1["source_authenticated"] = True  # Synthetic external-attestation fixture only.
        r = inspect(p2, i2, v2, previous_games=[g1])
        self.assertTrue(r["structural_validation_passed"])
        self.assertEqual(r["normalized_snapshot"]["side_by_team"], {"red-team": "blue", "blue-team": "red"})

    def test_own_hero_reuse(self):
        p1, i1, v1 = fixture(1)
        g1 = inspect(p1, i1, v1)["normalized_snapshot"]
        p2, i2, v2 = fixture(2)
        p2["bp_list"][10]["hero_id"] = g1["picks_by_team"]["red-team"][0]
        v2["sha256"] = canonical_digest(p2)
        self.assertIn("OWN_HERO_REUSE", inspect(p2, i2, v2, previous_games=[g1])["reasons"])

    def test_rights_self_assertion_not_trusted(self):
        p, i, v = fixture()
        v["source_authenticated"] = True
        v["license_granted"] = True
        r = inspect(p, i, v)
        self.assertFalse(r["provider_data_usage_rights_verified"])
        self.assertFalse(r["normalized_snapshot"]["source_authenticated"])

    def test_downstream_pr390_gate_still_holds_unverified(self):
        from research.kpl_v7_bp_evidence import audit_bp_snapshot
        p, i, v = fixture()
        normalized = inspect(p, i, v)["normalized_snapshot"]
        result = audit_bp_snapshot(normalized, [], now_utc=NOW)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("SOURCE_AUTHENTICATION_MISSING", result["reasons"])

    def test_reject_network_transport(self):
        p, i, v = fixture()
        v["transport"] = "AUTO_SCRAPER"
        self.assertIn("NETWORK_CAPTURE_NOT_SUPPORTED", inspect(p, i, v)["reasons"])

    def test_invalid_match_index_bool_sequence(self):
        p, i, v = fixture()
        i["battles"][0]["battle_seq"] = True
        self.assertIn("INVALID_MATCH_INDEX", inspect(p, i, v)["reasons"])

    def test_large_payload(self):
        p, i, v = fixture()
        p["extra"] = "X" * 140_000
        self.assertIn("INVALID_OR_OVERSIZED_PAYLOAD", inspect(p, i, v)["reasons"])

    def test_prior_unattested_cannot_pass_structure(self):
        p1, i1, v1 = fixture(1)
        g1 = inspect(p1, i1, v1)["normalized_snapshot"]
        p2, i2, v2 = fixture(2)
        r = inspect(p2, i2, v2, previous_games=[g1])
        self.assertIn("PRIOR_GAME_UNATTESTED", r["reasons"])
        self.assertFalse(r["structural_validation_passed"])

    def test_prior_battle_id_must_match_index(self):
        p1, i1, v1 = fixture(1)
        g1 = inspect(p1, i1, v1)["normalized_snapshot"]
        g1["source_authenticated"] = True
        g1["battle_id"] = "wrong-battle"
        p2, i2, v2 = fixture(2)
        self.assertIn("PRIOR_GAME_IDENTITY_MISMATCH",
                      inspect(p2, i2, v2, previous_games=[g1])["reasons"])

    def test_prior_side_must_match_index(self):
        p1, i1, v1 = fixture(1)
        g1 = inspect(p1, i1, v1)["normalized_snapshot"]
        g1["source_authenticated"] = True
        g1["side_by_team"] = {"blue-team": "red", "red-team": "blue"}
        p2, i2, v2 = fixture(2)
        self.assertIn("PRIOR_GAME_SIDE_MISMATCH",
                      inspect(p2, i2, v2, previous_games=[g1])["reasons"])

    def test_prior_must_have_complete_bp(self):
        p1, i1, v1 = fixture(1)
        g1 = inspect(p1, i1, v1)["normalized_snapshot"]
        g1["source_authenticated"] = True
        g1["bp_complete"] = False
        p2, i2, v2 = fixture(2)
        self.assertIn("PRIOR_GAME_BP_INVALID",
                      inspect(p2, i2, v2, previous_games=[g1])["reasons"])

    def test_prior_capture_cannot_follow_current(self):
        p1, i1, v1 = fixture(1)
        g1 = inspect(p1, i1, v1)["normalized_snapshot"]
        g1["source_authenticated"] = True
        g1["observed_at"] = "2026-11-03T12:05:45Z"
        p2, i2, v2 = fixture(2)
        self.assertIn("PRIOR_GAME_AFTER_CURRENT_CAPTURE",
                      inspect(p2, i2, v2, previous_games=[g1])["reasons"])

    def test_prior_pick_ban_conflict_is_invalid(self):
        p1, i1, v1 = fixture(1)
        g1 = inspect(p1, i1, v1)["normalized_snapshot"]
        g1["source_authenticated"] = True
        g1["bans_by_team"]["blue-team"][0] = g1["picks_by_team"]["blue-team"][0]
        p2, i2, v2 = fixture(2)
        self.assertIn("PRIOR_GAME_BP_INVALID",
                      inspect(p2, i2, v2, previous_games=[g1])["reasons"])

    def test_prior_source_url_exact_battle_id(self):
        p1, i1, v1 = fixture(1)
        g1 = inspect(p1, i1, v1)["normalized_snapshot"]
        g1["source_authenticated"] = True
        g1["source"] = "https://example.org/forged-bp"
        p2, i2, v2 = fixture(2)
        self.assertIn("PRIOR_GAME_SOURCE_MISMATCH",
                      inspect(p2, i2, v2, previous_games=[g1])["reasons"])


if __name__ == "__main__":
    unittest.main()
