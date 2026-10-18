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
            self.assertIn("needs: [publish, archive, attest_research, archive_provenance]", job)
        self.assertIn("needs.attest_research.result == 'failure'", notify)
        self.assertIn("needs.attest_research.result == 'success'", close)
        self.assertIn("needs.archive_provenance.result == 'failure'", notify)
        self.assertIn("needs.archive_provenance.result == 'success'", close)
        self.assertIn("needs.publish.result == 'success' && needs.archive.result == 'success' &&",
                      close)

    def test_durable_proof_archive_is_independent_and_uses_scoped_credentials(self):
        match = re.search(r"(?ms)^  archive_provenance:\n(.*?)(?=^  \w+:|\Z)", self.workflow)
        self.assertIsNotNone(match)
        job = match.group(1)
        self.assertIn("needs: attest_research", job)
        self.assertIn("if: ${{ github.ref == 'refs/heads/main' }}", job)
        permissions = job.split("    permissions:\n", 1)[1].split("    steps:", 1)[0]
        self.assertEqual(dict(re.findall(r"^      ([\w-]+): (\w+)$", permissions,
                                         re.MULTILINE)), {"contents": "write"})
        for required in (
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "persist-credentials: false", "actions/download-artifact@" + DOWNLOAD_SHA,
            "name: football-king-forecast-provenance", "path: proof",
            "gh auth setup-git --hostname github.com", "python ops/archive_forecast_provenance.py",
            "--proof proof", '--destination "$proof_worktree"',
            "git fetch --no-tags origin '+refs/heads/main:refs/remotes/origin/main'",
            'git worktree add --detach "$proof_worktree" refs/remotes/origin/main',
            'git -C "$proof_worktree" add -- "${changed[@]}"',
            'git -C "$proof_worktree" push origin HEAD:refs/heads/main',
            "for retry in 1 2 3 4 5; do",
        ):
            with self.subTest(required=required):
                self.assertIn(required, job)
        self.assertNotIn("secrets.", job)
        self.assertNotIn("run-id:", job)
        self.assertNotIn("github-token:", job)
        self.assertNotIn("git add -A", job)
        self.assertNotIn("--force", job.split(" push ", 1)[1].split("; then", 1)[0])
        for name in ("publish", "archive", "attest_research"):
            body = re.search(r"(?ms)^  " + name + r":\n(.*?)(?=^  \w+:|\Z)", self.workflow).group(1)
            dependencies = re.findall(r"^    needs: (.+)$", body, re.MULTILINE)
            self.assertFalse(any("archive_provenance" in value for value in dependencies))

    def test_recorded_time_audit_reverifies_same_run_with_trusted_context(self):
        job = re.search(r"(?ms)^  archive_provenance:\n(.*?)(?=^  \w+:|\Z)",
                        self.workflow).group(1)
        audit = job.split("      - name: Reverify provenance before auditing recorded kickoff times\n", 1)[1]
        audit = audit.split("\n      - name:", 1)[0]
        for required in (
            "GH_TOKEN: ${{ github.token }}", "set -euo pipefail",
            "python ops/forecast_provenance_audit.py", "--proof proof",
            '--source-sha "$GITHUB_SHA"', '--workflow-sha "$GITHUB_WORKFLOW_SHA"',
            '--run-id "$GITHUB_RUN_ID"', '--attempt "$GITHUB_RUN_ATTEMPT"',
            '--output "$RUNNER_TEMP/provenance-time-audit.json"',
        ):
            self.assertIn(required, audit)
        self.assertNotIn("continue-on-error", job)
        self.assertLess(job.index("Preserve original proof bytes"),
                        job.index("Reverify provenance before auditing"))
        self.assertIn("id: recorded_time_audit", job)
        self.assertIn("if: ${{ !cancelled() && (steps.recorded_time_audit.outcome == 'success' || steps.recorded_time_audit.outcome == 'failure') }}", job)
        upload = job.split("name: football-king-provenance-time-audit", 1)[1]
        self.assertIn("path: ${{ runner.temp }}/provenance-time-audit.json", upload)
        self.assertIn("if-no-files-found: error", upload)
        self.assertIn("retention-days: 90", upload)


if __name__ == "__main__":
    unittest.main()
