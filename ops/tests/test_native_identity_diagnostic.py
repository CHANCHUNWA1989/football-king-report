import copy
import unittest
from datetime import datetime, timezone
from ops.fixture_source_evidence import capture_batch, assemble
from ops.native_identity_diagnostic import audit

NOW = datetime(2026, 11, 28, 8, tzinfo=timezone.utc)


class NativeIdentityDiagnosticTests(unittest.TestCase):
    def doc(self, rows):
        raw = {"league": "bundesliga", "status": "READY_RESEARCH",
               "source": "OpenLigaDB", "source_url": "https://api.openligadb.de/getmatchdata/bl1/2026",
               "captured_utc": "2026-11-28T07:59:00+00:00", "matches": rows}
        return assemble([capture_batch("bundesliga", "2026-27", raw, NOW, replay=False)], NOW)

    def row(self, **kw):
        return {"date": "2026-11-29", "home": "A", "away": "B", "event_id": "openligadb:123",
                "kickoff_utc": "2026-11-29T12:00:00+00:00", "status": "SCHEDULED", **kw}

    def test_reported_native_not_authenticated(self):
        doc = self.doc([self.row()])
        before = copy.deepcopy(doc)
        r = audit(doc)
        self.assertEqual(doc, before)
        self.assertEqual(r["batches"][0]["counts"]["unique_reported_openligadb_id"], 1)
        self.assertFalse(r["native_identity_authenticated"])
        self.assertEqual(r["admitted_new_fixtures"], 0)

    def test_missing_id_not_invented(self):
        r = audit(self.doc([self.row(event_id=None, kickoff_utc=None)]))
        c = r["batches"][0]["counts"]
        self.assertEqual(c["missing_event_id"], 1)
        self.assertEqual(c["unique_exact_context_rows"], 1)
        self.assertEqual(c["missing_or_invalid_kickoff_rows"], 1)
        self.assertEqual(c["explicit_row_league"], 0)

    def test_same_context_collision_is_rejected(self):
        r = audit(self.doc([self.row(), self.row(event_id="openligadb:456")]))
        self.assertEqual(r["batches"][0]["counts"]["ambiguous_exact_fixture_rows"], 2)
        self.assertNotIn("unique_reported_openligadb_id", r["batches"][0]["counts"])

    def test_reused_native_id_across_distinct_contexts(self):
        r = audit(self.doc([self.row(), self.row(away="C")]))
        self.assertEqual(r["batches"][0]["counts"]["duplicate_event_id_rows"], 2)

    def test_bad_date_and_unknown_id(self):
        r = audit(self.doc([self.row(date="not-date"), self.row(event_id="guessed:123")]))
        c = r["batches"][0]["counts"]
        self.assertEqual(c["invalid_date_or_teams"], 1)
        self.assertEqual(c["other_unverified_event_id"], 1)
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_digest_tamper_rejected(self):
        doc = self.doc([self.row()])
        doc["batches"][0]["rows"][0]["home"] = "tampered"
        with self.assertRaisesRegex(ValueError, "SOURCE_BATCH_DIGEST"):
            audit(doc)
