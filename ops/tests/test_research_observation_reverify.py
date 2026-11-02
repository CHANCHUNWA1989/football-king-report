"""Reverify exact run-bound artifact bytes; no independent chat or quote proof."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_run_observation import publish
from research_observation_reverify import verify
from ops.tests.test_research_run_observation import sample, NOW

RID, ATTEMPT, SHA = "1234", "2", "a" * 40


class ResearchObservationReverifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.json"
        self.artifact = self.root / "artifact"
        self.source.write_bytes((json.dumps(sample()) + "\n").encode())
        publish(self.source, self.artifact, run_id=RID,
                attempt=ATTEMPT, sha=SHA, now=NOW)

    def verified(self):
        return verify(self.artifact, run_id=RID, attempt=ATTEMPT, sha=SHA)

    def test_replays_exact_original_bytes_and_run_context(self):
        report = self.verified()
        self.assertEqual(report["status"], "RESEARCH_ONLY")
        self.assertEqual(report["observed_count"], 3)
        self.assertEqual(report["eligible_at_observation_count"], 2)
        self.assertEqual(report["research_selections_sha256"],
                         hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertFalse(report["can_enter_formal_settlement_ledger"])
        self.assertFalse(report["independent_publication_timestamp_verified"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_hold_with_no_candidates_is_still_preserved(self):
        doc = sample()
        doc.update(status="HOLD", selected_count=0, review_count=0,
                   model_only_count=0, selections=[], reviews=[],
                   model_only_watchlist=[])
        self.source.write_text(json.dumps(doc))
        other = self.root / "empty-hold"
        publish(self.source, other, run_id=RID, attempt=ATTEMPT, sha=SHA, now=NOW)
        got = verify(other, run_id=RID, attempt=ATTEMPT, sha=SHA)
        self.assertEqual(got["status"], "HOLD")
        self.assertEqual(got["observed_count"], 0)
        self.assertEqual(got["certified_forward_samples"], 0)

    def test_modified_original_bytes_are_rejected(self):
        raw = self.artifact / "research_selections.json"
        raw.write_bytes(raw.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "RAW_RESEARCH_DIGEST_MISMATCH"):
            self.verified()

    def test_rehashed_but_changed_source_is_not_accepted_without_matching_manifest(self):
        raw = self.artifact / "research_selections.json"
        doc = json.loads(raw.read_bytes())
        doc["selections"][0]["direction"] = "AWAY"
        raw.write_text(json.dumps(doc))
        manifest = self.artifact / "observation.json"
        report = json.loads(manifest.read_text())
        report["research_selections_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "OBSERVATION_REPLAY_MISMATCH"):
            self.verified()

    def test_identity_mismatch_never_revalidates_other_run(self):
        for opts in ({"run_id": "1235", "attempt": ATTEMPT, "sha": SHA},
                     {"run_id": RID, "attempt": "3", "sha": SHA},
                     {"run_id": RID, "attempt": ATTEMPT, "sha": "b" * 40}):
            with self.subTest(opts=opts), self.assertRaisesRegex(
                    ValueError, "GITHUB_RUN_CONTEXT_MISMATCH"):
                verify(self.artifact, **opts)

    def test_manifest_forgery_and_missing_fields_rejected(self):
        manifest = self.artifact / "observation.json"
        original = json.loads(manifest.read_text())
        for mutate in (
            lambda d: d.update(certified_forward_samples=1),
            lambda d: d.update(can_enter_formal_settlement_ledger=True),
            lambda d: d.update(eligible_at_observation_count=100),
            lambda d: d.update(observed_utc_runner_clock="bad-time"),
            lambda d: d.update(fake_signed_by_github=True),
        ):
            doc = copy.deepcopy(original)
            mutate(doc)
            manifest.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):
                self.verified()

    def test_invalid_inventory_symlink_and_extra_files_fail_closed(self):
        extra = self.artifact / "extra-secret.txt"
        extra.write_text("extra")
        with self.assertRaisesRegex(ValueError, "INVALID_ARTIFACT_FILE_INVENTORY"):
            self.verified()
        extra.unlink()
        raw = self.artifact / "research_selections.json"
        raw.unlink()
        raw.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "UNSAFE_ARTIFACT_FILE"):
            self.verified()

    def test_workflow_reverifies_before_uploading_artifact(self):
        workflow = (Path(__file__).resolve().parents[2]
                    / ".github/workflows/football-king-iphone.yml").read_text()
        c = workflow.index("Capture research decisions as run-bound observations")
        v = workflow.index("Reverify run-bound research decision observation")
        u = workflow.index("Upload run-bound research decision observation")
        self.assertLess(c, v)
        self.assertLess(v, u)
        self.assertIn("python ops/research_observation_reverify.py", workflow)


if __name__ == "__main__":
    unittest.main()
