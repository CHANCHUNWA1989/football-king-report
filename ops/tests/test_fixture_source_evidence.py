import copy
import unittest
from datetime import datetime, timezone
from ops.fixture_source_evidence import capture_batch, assemble, digest
from ops.shadow_forecast import generate

NOW = datetime(2026, 11, 28, 8, tzinfo=timezone.utc)


class FixtureSourceEvidenceTests(unittest.TestCase):
    def raw(self):
        return {"status": "READY_RESEARCH", "league": "epl",
                "source": "synthetic", "source_url": "https://example.invalid",
                "captured_utc": "2026-11-28T07:59:00+00:00",
                "matches": [{"home": "Arsenal", "away": "Everton",
                             "date": "2026-11-28", "status": "UNCONFIRMED"}]}

    def test_preserves_null_identity_and_original_rows(self):
        raw = self.raw()
        before = copy.deepcopy(raw)
        b = capture_batch("epl", "2026-27", raw, NOW, replay=True)
        self.assertEqual(raw, before)
        self.assertEqual(b["requested_league"], "epl")
        self.assertIsNone(b["rows"][0]["league"])
        self.assertIsNone(b["rows"][0]["event_id"])
        self.assertEqual(b["projection_sha256"], digest(b["rows"]))
        self.assertFalse(b["identity_authenticated"])

    def test_rejects_conflicting_row_and_batch_league(self):
        raw = self.raw()
        raw["matches"][0]["league"] = "championship"
        b = capture_batch("epl", "2026-27", raw, NOW, replay=True)
        self.assertEqual(b["rows"], [])
        self.assertEqual(b["rejected"]["ROW_COMPETITION_CONFLICT"], 1)
        raw["league"] = "seriea"
        self.assertEqual(capture_batch("epl", "2026-27", raw, NOW, replay=True)["status"], "HOLD")

    def test_future_timestamp_and_missing_source_hold(self):
        raw = self.raw()
        raw["captured_utc"] = "2026-11-28T09:00:00+00:00"
        self.assertEqual(capture_batch("epl", "2026-27", raw, NOW, replay=True)["status"], "HOLD")
        raw = self.raw()
        raw.pop("source")
        self.assertEqual(capture_batch("epl", "2026-27", raw, NOW, replay=True)["status"], "HOLD")

    def test_opt_in_generator_does_not_call_extra_sources_or_change_output(self):
        calls = []
        def getter(season, league, clock):
            calls.append(league)
            return self.raw() if league == "epl" else {"status": "HOLD"}
        base = generate(now=NOW, getter=getter)
        expected_calls = list(calls)
        calls.clear()
        result = generate(now=NOW, getter=getter, return_source_evidence=True)
        evidence = result.pop("_internal_source_evidence")
        self.assertEqual(base, result)
        self.assertEqual(calls, expected_calls)
        self.assertEqual(evidence["batch_count"], 1)
        self.assertTrue(evidence["batches"][0]["replay"])
        self.assertEqual(evidence["production_recommendations"], "DISABLED")
        self.assertEqual(evidence["admitted_new_fixtures"], 0)

    def test_no_admission_even_when_context_complete(self):
        b = capture_batch("epl", "2026-27", self.raw(), NOW, replay=True)
        d = assemble([b], NOW)
        self.assertFalse(d["missing_gateway_fixtures_proven"])
        self.assertFalse(d["competition_identity_authenticated"])
        self.assertEqual(d["status"], "HOLD")

    def test_live_artifact_verification_and_tampering(self):
        from ops.fixture_source_evidence import verify_for_artifact
        raw = self.raw()
        raw["source_url"] = "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/en.1.json"
        b = capture_batch("epl", "2026-27", raw, NOW, replay=False)
        d = assemble([b], NOW)
        self.assertEqual(verify_for_artifact(d)["normalized_projection_rows"], 1)
        self.assertEqual(verify_for_artifact(d)["rows_with_explicit_league"], 0)
        d["batches"][0]["rows"][0]["home"] = "changed"
        with self.assertRaisesRegex(ValueError, "SOURCE_BATCH_DIGEST"):
            verify_for_artifact(d)

    def test_artifact_rejects_unapproved_url_and_replay(self):
        from ops.fixture_source_evidence import verify_for_artifact
        raw = self.raw()
        with self.assertRaisesRegex(ValueError, "SOURCE_URL_NOT_PUBLIC_ALLOWLIST"):
            verify_for_artifact(assemble([capture_batch("epl", "2026-27", raw, NOW, replay=False)], NOW))
        with self.assertRaisesRegex(ValueError, "REPLAY_NOT_LIVE"):
            verify_for_artifact(assemble([capture_batch("epl", "2026-27", raw, NOW, replay=True)], NOW))
