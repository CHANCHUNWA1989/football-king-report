import copy
import hashlib
import json
import unittest
from ops.public_snapshot_identity_audit import audit


class PublicSnapshotIdentityAuditTest(unittest.TestCase):
    def setUp(self):
        self.row = {"league": "epl", "event_id": "native:1",
                    "home": "Arsenal", "away": "Everton",
                    "source": "example", "source_url": "https://example.invalid",
                    "source_captured_utc": "2026-11-28T07:00:00+00:00",
                    "kickoff_utc": "2026-11-28T12:00:00+00:00",
                    "eligible_for_prematch_evaluation": True}

    def doc(self, rows):
        raw = json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()
        return {"schema": "football-king-public-asof-1",
                "production_recommendations": "DISABLED",
                "as_of_utc": "2026-11-28T08:00:00+00:00",
                "observations": rows, "event_count": len(rows),
                "observations_sha256": hashlib.sha256(raw).hexdigest()}

    def test_complete_metadata_is_not_authentication(self):
        r = audit(self.doc([self.row]))
        self.assertEqual(r["explicit_identity_metadata_ready"], 1)
        self.assertFalse(r["source_identity_authenticated"])
        self.assertFalse(r["missing_gateway_fixtures_proven"])
        self.assertEqual(r["admitted_new_fixtures"], 0)
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_missing_league_not_inferred_from_names(self):
        row = dict(self.row, league=None, event_id=None)
        r = audit(self.doc([row]))
        self.assertEqual(r["missing_fields"]["league"], 1)
        self.assertEqual(r["explicit_identity_metadata_ready"], 0)

    def test_duplicate_native_id_and_wrong_league(self):
        r = audit(self.doc([self.row, dict(self.row, away="Chelsea"),
                            dict(self.row, league="unknown")]))
        self.assertEqual(r["explicit_identity_metadata_ready"], 0)
        self.assertEqual(r["rejected"]["AMBIGUOUS_EVENT_ID"], 2)

    def test_future_capture_and_near_kickoff_rejected(self):
        r = audit(self.doc([dict(self.row, source_captured_utc="2026-11-28T09:00:00+00:00"),
                            dict(self.row, event_id="native:2", kickoff_utc="2026-11-28T08:10:00+00:00")]))
        self.assertEqual(r["rejected"]["INVALID_OR_LATE_CLOCK"], 2)

    def test_digest_mismatch_and_disabled_guard(self):
        d = self.doc([copy.deepcopy(self.row)])
        d["observations"][0]["league"] = "championship"
        with self.assertRaisesRegex(ValueError, "OBSERVATION_DIGEST_MISMATCH"):
            audit(d)
        d = self.doc([self.row])
        d["production_recommendations"] = "ENABLED"
        with self.assertRaisesRegex(ValueError, "INVALID_RESEARCH_SNAPSHOT"):
            audit(d)
