"""Integration contract for signing public forecasts without promoting them.

These policy checks do not simulate or certify cryptographic verification;
the hosted main-branch job must verify genuine bundles and reject both attacks.
"""
import re
import unittest
from pathlib import Path


WORKFLOW = (Path(__file__).resolve().parents[2] / ".github/workflows/"
            "football-king-iphone.yml")
ATTEST_SHA = "1e69f48acb82d1966a394da916b4c1698aa569d6"
DOWNLOAD_SHA = "d3f86a106a0bac45b974a628896c90dbdf5c8093"
UPLOAD_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"


class ForecastProvenancePolicyTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(r"(?ms)^  attest_research:\n(.*?)(?=^  \w+:|\Z)",
                          self.workflow)
        self.assertIsNotNone(match, "Public forecasts need a separate provenance job")
        self.job = match.group(1)

    def test_only_successful_hosted_main_run_can_sign_with_minimal_permissions(self):
        self.assertIn("needs: publish", self.job)
        self.assertIn("if: ${{ github.ref == 'refs/heads/main' }}", self.job)
        self.assertIn("runs-on: ubuntu-latest", self.job)
        self.assertIn("timeout-minutes: 8", self.job)
        permissions = self.job.split("    permissions:\n", 1)[1].split("    steps:", 1)[0]
        self.assertEqual(dict(re.findall(r"^      ([\w-]+): (\w+)$", permissions,
                                         re.MULTILINE)),
                         {"contents": "read", "id-token": "write", "attestations": "write"})
        self.assertNotIn("secrets.", self.job)
        self.assertNotIn("actions/checkout@", self.job)
        self.assertNotIn("continue-on-error", self.job)

    def test_only_three_explicit_public_subjects_from_same_run_are_signed(self):
        self.assertIn("actions/download-artifact@" + DOWNLOAD_SHA, self.job)
        download = self.job.split("actions/download-artifact@", 1)[1].split("\n      - name:", 1)[0]
        self.assertIn("name: football-king-research-snapshots", download)
        self.assertIn("path: snapshot", download)
        self.assertNotIn("run-id:", download)
        self.assertNotIn("github-token:", download)
        self.assertIn("actions/attest@" + ATTEST_SHA, self.job)
        self.assertNotIn("attest-build-provenance", self.job)
        subjects = re.search(r"(?m)^          subject-path: \|\n((?:            .+\n)+)",
                             self.job).group(1)
        self.assertEqual(subjects.split(), ["snapshot/shadow.json", "snapshot/paired.json",
                                           "snapshot/slate.json"])
        self.assertIn("push-to-registry: false", self.job)
        self.assertIn("create-storage-record: false", self.job)

    def test_real_verification_binds_bundle_identity_and_both_commit_digests(self):
        for required in (
            "ATTESTATION_BUNDLE: ${{ steps.attest.outputs.bundle-path }}",
            'cp "$ATTESTATION_BUNDLE" provenance/research.sigstore.json',
            'gh attestation verify "$artifact"',
            '--bundle provenance/research.sigstore.json',
            '--repo "$GITHUB_REPOSITORY"',
            '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/football-king-iphone.yml"',
            '--source-ref "$GITHUB_REF"',
            'local source_digest="${2:-$GITHUB_SHA}"',
            '--source-digest "$source_digest"',
            '--signer-digest "$GITHUB_WORKFLOW_SHA"',
            '--deny-self-hosted-runners',
            '--format json',
            'for name in shadow paired slate; do',
            'verify_snapshot "snapshot/$name.json" > "provenance/$name.verification.json"',
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.job)
        self.assertEqual(self.job.count("GH_TOKEN: ${{ github.token }}"), 1)
        self.assertNotIn("set -x", self.job)

    def test_tampered_bytes_and_wrong_source_commit_must_be_rejected(self):
        self.assertIn('cp snapshot/shadow.json "$tampered"', self.job)
        self.assertIn("printf '\\n' >> \"$tampered\"", self.job)
        self.assertRegex(self.job, r'if verify_snapshot "\$tampered"[^\n]*; then\n'
                                  r'(?:.*\n)*?            exit 1\n          fi')
        self.assertRegex(self.job, r'if verify_snapshot snapshot/shadow.json "0{40}"'
                                  r'[^\n]*; then\n(?:.*\n)*?            exit 1\n          fi')
        self.assertIn('"tampered_subject_rejected":true', self.job)
        self.assertIn('"wrong_source_digest_rejected":true', self.job)

    def test_upload_keeps_reverifiable_public_evidence_only_after_success(self):
        upload = self.job.split("actions/upload-artifact@" + UPLOAD_SHA, 1)[1]
        self.assertIn("name: football-king-forecast-provenance", upload)
        self.assertIn("path: provenance/", upload)
        self.assertIn("retention-days: 90", upload)
        self.assertIn("if-no-files-found: error", upload)
        self.assertNotIn("always()", self.job)
        self.assertIn('cp "snapshot/$name.json" "provenance/$name.json"', self.job)
        self.assertNotIn("settled.json", self.job)
        self.assertNotIn("private", self.job)
        self.assertIn('production_recommendations', self.workflow)
        self.assertIn("DISABLED", self.workflow)

    def test_incidents_include_provenance_failure_and_require_recovery(self):
        notify = self.workflow.split("  notify_failure:\n", 1)[1].split(
            "  close_resolved_incident:\n", 1)[0]
        close = self.workflow.split("  close_resolved_incident:\n", 1)[1]
        for job in (notify, close):
            self.assertIn("needs: [publish, archive, attest_research]", job)
        self.assertIn("needs.attest_research.result == 'failure'", notify)
        self.assertIn("needs.attest_research.result == 'success'", close)
        self.assertIn("needs.publish.result == 'success' && needs.archive.result == 'success' &&",
                      close)


if __name__ == "__main__":
    unittest.main()
