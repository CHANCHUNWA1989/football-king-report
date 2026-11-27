import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock

from ops.pages_artifact_visibility import classify, wait_visible


def row(**changes):
    return dict({"name": "github-pages", "expired": False, "id": 123,
                 "size_in_bytes": 100}, **changes)


def page(*rows):
    return {"total_count": len(rows), "artifacts": list(rows)}


class PagesArtifactVisibilityTests(unittest.TestCase):
    def test_hosted_canary_verifies_the_upload_in_a_dependent_job(self):
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/"
                    / "pages-artifact-visibility-canary.yml").read_text(encoding="utf-8")
        self.assertIn("pages_artifact_id: ${{ steps.pages_upload.outputs.artifact_id }}", workflow)
        self.assertIn("needs: upload", workflow)
        self.assertIn("EXPECTED_PAGES_ARTIFACT_ID: ${{ needs.upload.outputs.pages_artifact_id }}", workflow)
        self.assertNotIn("uses: actions/deploy-pages@", workflow)

    def test_unique(self):
        self.assertEqual(classify(page(row(), row(name="other"))), "READY")

    def test_invalid_and_incomplete(self):
        for payload in (None, {}, page(), page(row(expired=True)),
                        page(row(size_in_bytes=0)), page(row(id=True)),
                        page(row(size_in_bytes=True)), page(row(expired=0)),
                        {"total_count": 2, "artifacts": [row()]},
                        page(None), page(row(name=None))):
            with self.subTest(payload=payload):
                self.assertEqual(classify(payload), "WAIT")

    def test_duplicate_even_if_expired_or_empty(self):
        for second in (row(id=124), row(id=124, expired=True),
                       row(id=124, size_in_bytes=0)):
            self.assertEqual(classify(page(row(), second)), "REJECT")

    def test_delayed_visibility(self):
        fetch = Mock(side_effect=[page(), page(), page(row())])
        pause = Mock()
        self.assertEqual(wait_visible(fetch, pause), 0)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(pause.call_count, 2)

    def test_timeout_and_recovery(self):
        fetch = Mock(side_effect=[subprocess.TimeoutExpired("gh", 10),
                                  ValueError(), page(row())])
        self.assertEqual(wait_visible(fetch, Mock()), 0)

    def test_exhaustion(self):
        fetch, pause = Mock(return_value=page()), Mock()
        self.assertEqual(wait_visible(fetch, pause), 1)
        self.assertEqual(fetch.call_count, 6)
        self.assertEqual(pause.call_count, 5)

    def test_ambiguous_fails_immediately(self):
        fetch, pause = Mock(return_value=page(row(), row(id=124))), Mock()
        self.assertEqual(wait_visible(fetch, pause), 2)
        fetch.assert_called_once()
        pause.assert_not_called()

    def test_exact_upload_id(self):
        self.assertEqual(classify(page(row()),123),"READY")
        self.assertEqual(classify(page(row(id=124)),123),"REJECT")
        fetch=Mock(return_value=page(row(id=124)))
        pause=Mock()
        self.assertEqual(wait_visible(fetch,pause,expected_id=123),2)
        fetch.assert_called_once()
        pause.assert_not_called()

    def test_invalid_expected_id_rejected_before_fetch(self):
        for invalid in (True, False, 0, -1, 2**63, "123", 123.0):
            with self.subTest(invalid=invalid):
                self.assertEqual(classify(page(row()), invalid), "REJECT")
                fetch, pause = Mock(return_value=page(row())), Mock()
                self.assertEqual(wait_visible(fetch, pause, expected_id=invalid), 2)
                fetch.assert_not_called()
                pause.assert_not_called()

    def test_expected_id_cannot_belong_to_other_artifact(self):
        for payload in (page(row(name="research", id=123)),
                        page(row(), row(name="research", id=123)),
                        page(row(id=124), row(name="research", id=123))):
            with self.subTest(payload=payload):
                self.assertEqual(classify(payload, 123), "REJECT")
        self.assertEqual(classify(page(row(name="research", id=999)), 123), "WAIT")
        self.assertEqual(classify(page(row(), row(name="research", id=999)), 123), "READY")
