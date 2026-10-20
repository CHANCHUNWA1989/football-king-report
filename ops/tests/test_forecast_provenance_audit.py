"""Policy tests using mocked gh stdout, never proof of cryptographic validity."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forecast_provenance_audit import audit, main


REPO = "CHANCHUNWA1989/football-king-report"
URI = "https://github.com/" + REPO
WORKFLOW = URI + "/.github/workflows/football-king-iphone.yml@refs/heads/main"
SOURCE = "1" * 40
WORKFLOW_SHA = "2" * 40
RUN = "39133031901"
WITNESS = "2026-10-18T13:48:29Z"
IDENTITY_KEYS = ("league", "home", "away", "kickoff_utc", "prediction_utc")


class ForecastProvenanceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proof = Path(self.temp.name)
        self.now = datetime(2026, 10, 18, 14, tzinfo=timezone.utc)
        self.options = dict(source_sha=SOURCE, workflow_sha=WORKFLOW_SHA,
                            run_id=RUN, attempt="1", now=self.now)
        self.pair = {
            "case_id": "case-1", "league": "bundesliga", "home": "Bayern",
            "away": "Dortmund", "kickoff_utc": "2026-10-18T15:30:00+00:00",
            "prediction_utc": "2026-10-18T13:46:59+00:00",
            "market_snapshot_utc": "2026-10-18T13:30:25+00:00",
            "market_updated_utc": "2026-10-18T13:29:19+00:00",
            "market_event_id": "market-event-1",
            "model": [.65, .2, .15], "market": [.6, .25, .15],
            "available_for_betting": False, "production_recommendations": "DISABLED",
        }
        self.forecast = {k: self.pair[k] for k in (
            "league", "home", "away", "kickoff_utc", "prediction_utc",
            "production_recommendations")}
        self.forecast.update(event_id="forecast-1", p_home=.65, p_draw=.2, p_away=.15)
        self.shadow = {"schema": "football-king-uncalibrated-shadow-1",
                       "status": "SHADOW_ONLY", "as_of_utc": self.pair["prediction_utc"],
                       "predictions_count": 1, "predictions": [self.forecast],
                       "production_recommendations": "DISABLED"}
        self.paired = {"status": "RESEARCH_ONLY", "matched_count": 1,
                       "comparisons": [self.pair], "production_recommendations": "DISABLED"}
        self.slate = {"schema": "football-king-forward-pick-verification-slate-v1",
                      "verification_rows": 0, "point_in_time_market_pairs": 1, "rows": [],
                      "production_recommendations": "DISABLED"}
        # Shape follows the real CLI schema; this is deliberately NOT a signed bundle.
        self.bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                       "dsseEnvelope": {"payload": "MOCK_NOT_CRYPTOGRAPHIC_PROOF"}}
        self.cert = {
            "issuer": "https://token.actions.githubusercontent.com",
            "subjectAlternativeName": WORKFLOW, "buildSignerURI": WORKFLOW,
            "buildConfigURI": WORKFLOW, "githubWorkflowRepository": REPO,
            "githubWorkflowRef": "refs/heads/main", "githubWorkflowSHA": WORKFLOW_SHA,
            "sourceRepositoryURI": URI, "sourceRepositoryDigest": SOURCE,
            "sourceRepositoryRef": "refs/heads/main", "buildSignerDigest": WORKFLOW_SHA,
            "buildConfigDigest": WORKFLOW_SHA, "runnerEnvironment": "github-hosted",
            "sourceRepositoryIdentifier": "1411226578",
            "sourceRepositoryOwnerURI": "https://github.com/CHANCHUNWA1989",
            "sourceRepositoryOwnerIdentifier": "339931460",
            "runInvocationURI": URI + "/actions/runs/" + RUN + "/attempts/1",
        }
        self.write_inputs()

    def write_inputs(self):
        for name, doc in (("shadow", self.shadow), ("paired", self.paired),
                          ("slate", self.slate), ("research.sigstore", self.bundle)):
            (self.proof / (name + ".json")).write_text(json.dumps(doc) + "\n")

    def stdout(self):
        subjects = [{"name": name + ".json", "digest": {"sha256": hashlib.sha256(
            (self.proof / (name + ".json")).read_bytes()).hexdigest()}}
                    for name in ("shadow", "paired", "slate")]
        return [{"attestation": {"bundle": self.bundle}, "verificationResult": {
            "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
            "signature": {"certificate": copy.deepcopy(self.cert)},
            "verifiedTimestamps": [{"type": "Tlog", "uri": "https://rekor.sigstore.dev",
                                     "timestamp": WITNESS}],
            "statement": {"_type": "https://in-toto.io/Statement/v1", "subject": subjects,
                          "predicateType": "https://slsa.dev/provenance/v1",
                          "predicate": {"untrusted_claimed_time": "1999-01-01T00:00:00Z"}},
        }}]

    def run_audit(self, stdout=None, **options):
        output = json.dumps(self.stdout() if stdout is None else stdout).encode()
        with patch("forecast_provenance_audit.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, output, b"")) as run:
            result = audit(self.proof, **dict(self.options, **options))
        return result, run

    def slate_entry(self):
        entry = {key: self.pair[key] for key in IDENTITY_KEYS + (
            "case_id", "market_snapshot_utc", "market_updated_utc", "production_recommendations")}
        entry.update(model_probabilities_1x2=self.pair["model"],
                     earlier_market_consensus_probabilities_1x2=self.pair["market"])
        anchor = [self.pair[key] for key in ("case_id",) + IDENTITY_KEYS]
        anchor.extend([self.pair["model"], self.pair["market"]])
        entry["sealed_pick_digest"] = hashlib.sha256(json.dumps(
            anchor, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return entry

    def assert_held(self, result, observed=0):
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["immutable_forecast_evidence_verified"])
        self.assertFalse(result["outcomes_independently_authenticated"])
        self.assertFalse(result["recorded_kickoff_independently_authenticated"])
        self.assertEqual(result["observed_before_recorded_kickoff_count"], observed)

    def test_current_cli_stdout_can_establish_recorded_time_only(self):
        result, run = self.run_audit()
        self.assert_held(result, 1)
        self.assertTrue(result["audit_completed"])
        self.assertEqual(result["total_pairs"], 1)
        self.assertEqual(result["slate_row_count"], 0)  # Slate is only a subset.
        self.assertEqual(run.call_count, 3)
        for call, name in zip(run.call_args_list, ("shadow", "paired", "slate")):
            argv = call.args[0]
            self.assertIsInstance(argv, list)
            self.assertEqual(argv[:3], ["gh", "attestation", "verify"])
            self.assertEqual(argv[3], str(self.proof / (name + ".json")))
            for flag, value in (("--repo", REPO), ("--source-ref", "refs/heads/main"),
                                ("--source-digest", SOURCE), ("--signer-digest", WORKFLOW_SHA)):
                self.assertEqual(argv[argv.index(flag) + 1], value)
            self.assertIn("--deny-self-hosted-runners", argv)
            self.assertEqual(call.kwargs["timeout"], 30)
            self.assertFalse(call.kwargs.get("shell", False))
            self.assertNotIn("env", call.kwargs)  # Preserve normal GH authentication.

    def test_fixed_identity_is_preserved_but_never_authenticates_results(self):
        self.forecast["event_id"] = "openligadb:83212"
        self.pair.update(
            forecast_event_id="openligadb:83212",
            source_fixture_identity={"provider": "OpenLigaDB", "match_id": "83212"},
            source_fixture_identity_status="UNAUTHENTICATED",
            independently_verified=False, eligible_for_model_scoring=False)
        self.write_inputs()
        result, _ = self.run_audit()
        self.assert_held(result, 1)
        self.assertFalse(result["eligible_for_betting_promotion"])
        self.assertEqual(result["cases"][0]["forecast_event_id"], "openligadb:83212")
        self.assertEqual(result["cases"][0]["source_fixture_identity"],
                         {"provider": "OpenLigaDB", "match_id": "83212"})

    def test_signed_pair_identity_must_match_original_shadow_event(self):
        self.forecast["event_id"] = "openligadb:83212"
        for changed in (
                {"forecast_event_id": "openligadb:83213",
                 "source_fixture_identity": {"provider": "OpenLigaDB", "match_id": "83213"}},
                {"source_fixture_identity": {"provider": "OpenLigaDB", "match_id": "83213"}},
                {"source_fixture_identity": {"provider": "OpenLigaDB", "match_id": True}},
                {"source_fixture_identity_status": "VERIFIED"},
                {"independently_verified": True},
                {"eligible_for_model_scoring": True},
                {"forecast_event_id": "openligadb:０８３２１２"}):
            with self.subTest(changed=changed):
                self.pair.update(
                    forecast_event_id="openligadb:83212",
                    source_fixture_identity={"provider": "OpenLigaDB", "match_id": "83212"},
                    source_fixture_identity_status="UNAUTHENTICATED",
                    independently_verified=False, eligible_for_model_scoring=False)
                self.pair.update(changed)
                self.write_inputs()
                result, _ = self.run_audit()
                self.assert_held(result)
                self.assertTrue(result["audit_completed"])
                self.assertEqual(result["cases"][0]["reason"],
                                 "PAIRED_FORECAST_SOURCE_IDENTITY_CONFLICT")

    def test_saved_verification_json_cannot_bypass_cli_failure(self):
        for name in ("shadow", "paired", "slate"):
            (self.proof / (name + ".verification.json")).write_text(json.dumps(self.stdout()))
        for failure in (FileNotFoundError(), subprocess.TimeoutExpired("gh", 30),
                        subprocess.CompletedProcess([], 1, b"[]", b"private error"),
                        subprocess.CompletedProcess([], 0, b"", b""),
                        subprocess.CompletedProcess([], 0, b"not json", b"")):
            with self.subTest(failure=type(failure).__name__):
                kw = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
                with patch("forecast_provenance_audit.subprocess.run", **kw):
                    result = audit(self.proof, **self.options)
                self.assert_held(result)
                self.assertFalse(result["audit_completed"])
                self.assertNotIn("private error", json.dumps(result))

    def test_certificate_identity_source_workflow_run_and_host_are_pinned(self):
        for field in self.cert:
            with self.subTest(field=field):
                output = self.stdout()
                output[0]["verificationResult"]["signature"]["certificate"][field] = "wrong"
                result, _ = self.run_audit(output)
                self.assert_held(result)
                self.assertFalse(result["audit_completed"])

    def test_result_certificate_subject_and_timestamp_ambiguity_is_rejected(self):
        for kind in ("no_result", "two_results", "certificate_list", "extra_subject",
                     "duplicate_subject", "path_subject", "wrong_digest", "wrong_bundle",
                     "two_timestamps", "missing_timestamp", "predicate_time_only",
                     "wrong_tlog", "wrong_uri", "naive_time", "non_utc_time", "future_time"):
            with self.subTest(kind=kind):
                output = self.stdout()
                vr = output[0]["verificationResult"]
                if kind == "no_result": output = []
                elif kind == "two_results": output *= 2
                elif kind == "certificate_list": vr["signature"]["certificate"] = [self.cert]
                elif kind == "extra_subject": vr["statement"]["subject"].append({"name": "extra"})
                elif kind == "duplicate_subject": vr["statement"]["subject"][1] = vr["statement"]["subject"][0]
                elif kind == "path_subject": vr["statement"]["subject"][0]["name"] = "snapshot/shadow.json"
                elif kind == "wrong_digest": vr["statement"]["subject"][0]["digest"]["sha256"] = "0" * 64
                elif kind == "wrong_bundle": output[0]["attestation"]["bundle"] = {"other": True}
                elif kind == "two_timestamps": vr["verifiedTimestamps"] *= 2
                elif kind in ("missing_timestamp", "predicate_time_only"): vr["verifiedTimestamps"] = []
                elif kind == "wrong_tlog": vr["verifiedTimestamps"][0]["type"] = "RFC3161"
                elif kind == "wrong_uri": vr["verifiedTimestamps"][0]["uri"] = "https://rekor.example"
                elif kind == "naive_time": vr["verifiedTimestamps"][0]["timestamp"] = "2026-10-18T13:48:29"
                elif kind == "non_utc_time": vr["verifiedTimestamps"][0]["timestamp"] = "2026-10-18T14:48:29+01:00"
                elif kind == "future_time": vr["verifiedTimestamps"][0]["timestamp"] = "2026-10-18T14:05:01Z"
                result, _ = self.run_audit(output)
                self.assert_held(result)
                self.assertFalse(result["audit_completed"])

    def test_late_witness_missing_conflicting_or_duplicate_forecasts_not_counted(self):
        for kind in ("late", "prediction_after_witness", "market_after_prediction", "updated_after_snapshot",
                     "missing_shadow", "wrong_vector", "duplicate_shadow", "duplicate_case", "result_present"):
            with self.subTest(kind=kind):
                shadow, paired = copy.deepcopy(self.shadow), copy.deepcopy(self.paired)
                if kind == "late":
                    self.pair["kickoff_utc"] = self.forecast["kickoff_utc"] = "2026-10-18T13:58:28+00:00"
                elif kind == "prediction_after_witness":
                    self.pair["prediction_utc"] = self.forecast["prediction_utc"] = "2026-10-18T13:49:00+00:00"
                    self.shadow["as_of_utc"] = self.pair["prediction_utc"]
                elif kind == "market_after_prediction": self.pair["market_snapshot_utc"] = "2026-10-18T13:47:59+00:00"
                elif kind == "updated_after_snapshot": self.pair["market_updated_utc"] = "2026-10-18T13:31:00+00:00"
                elif kind == "missing_shadow": self.forecast["home"] = "Other Home"
                elif kind == "wrong_vector": self.pair["model"] = [.6, .2, .2]
                elif kind == "duplicate_shadow":
                    self.shadow["predictions"].append(copy.deepcopy(self.forecast));self.shadow["predictions_count"] = 2
                elif kind == "duplicate_case":
                    self.paired["comparisons"].append(copy.deepcopy(self.pair));self.paired["matched_count"] = 2
                    self.slate["point_in_time_market_pairs"] = 2
                elif kind == "result_present": self.pair["result"] = 0
                self.write_inputs()
                result, _ = self.run_audit()
                self.assert_held(result)
                self.assertTrue(result["audit_completed"])
                self.assertTrue(all(row["reason"] != "OBSERVED_BEFORE_RECORDED_KICKOFF" for row in result["cases"]))
                self.shadow, self.paired = shadow, paired
                self.forecast, self.pair = self.shadow["predictions"][0], self.paired["comparisons"][0]
                self.slate["point_in_time_market_pairs"] = 1

    def test_ten_minute_boundary_and_future_clock_tolerance(self):
        self.pair["kickoff_utc"] = self.forecast["kickoff_utc"] = "2026-10-18T13:58:29+00:00"
        self.write_inputs()
        result, _ = self.run_audit(now=datetime(2026, 10, 18, 13, 43, 29, tzinfo=timezone.utc))
        self.assert_held(result, 1)

    def test_same_source_event_or_fixture_cannot_count_as_two_cases(self):
        for kind in ("same_market_event", "same_shadow_event", "different_forecast_same_fixture",
                     "equivalent_kickoff", "missing_market_event", "missing_shadow_event"):
            with self.subTest(kind=kind):
                pair, forecast = copy.deepcopy(self.pair), copy.deepcopy(self.forecast)
                pair.update(case_id="case-2", market_event_id="market-event-2")
                forecast["event_id"] = "forecast-2"
                if kind not in ("different_forecast_same_fixture", "equivalent_kickoff"):
                    pair["home"] = forecast["home"] = "Other Home"
                    pair["away"] = forecast["away"] = "Other Away"
                if kind == "same_market_event": pair["market_event_id"] = self.pair["market_event_id"]
                if kind == "same_shadow_event": forecast["event_id"] = self.forecast["event_id"]
                if kind == "different_forecast_same_fixture":
                    forecast["prediction_utc"] = "2026-10-18T13:46:58+00:00"
                if kind == "equivalent_kickoff":
                    pair["kickoff_utc"] = forecast["kickoff_utc"] = "2026-10-18T15:30:00Z"
                if kind == "missing_market_event":
                    pair.pop("market_event_id")
                    self.pair.pop("market_event_id", None)
                if kind == "missing_shadow_event":
                    forecast.pop("event_id")
                    self.forecast.pop("event_id", None)
                self.shadow.update(predictions=[self.forecast, forecast], predictions_count=2)
                self.paired.update(comparisons=[self.pair, pair], matched_count=2)
                self.slate["point_in_time_market_pairs"] = 2
                self.write_inputs()
                result, _ = self.run_audit()
                self.assert_held(result)
                self.pair["market_event_id"] = "market-event-1"
                self.forecast["event_id"] = "forecast-1"

    def test_slate_is_an_exact_bounded_subset_and_not_the_cohort_denominator(self):
        self.slate.update(rows=[self.slate_entry()], verification_rows=1)
        self.write_inputs()
        result, _ = self.run_audit()
        self.assert_held(result, 1)
        self.assertTrue(result["cases"][0]["listed_in_slate"])
        for kind in ("vector_conflict", "market_conflict", "anchor_conflict", "unknown_case",
                     "duplicate_case", "too_many_rows"):
            with self.subTest(kind=kind):
                entry = self.slate_entry()
                rows = [entry]
                if kind == "vector_conflict": entry["model_probabilities_1x2"] = [.6, .2, .2]
                elif kind == "market_conflict": entry["market_snapshot_utc"] = "2026-10-18T13:30:24+00:00"
                elif kind == "anchor_conflict": entry["sealed_pick_digest"] = "0" * 64
                elif kind == "unknown_case": entry["case_id"] = "not-in-paired"
                elif kind == "duplicate_case": rows *= 2
                elif kind == "too_many_rows": rows *= 101
                self.slate.update(rows=rows, verification_rows=len(rows))
                self.write_inputs()
                result, _ = self.run_audit()
                self.assert_held(result)

    def test_three_successful_cli_outputs_must_be_the_same_attestation(self):
        first, changed = self.stdout(), self.stdout()
        changed[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = "2026-10-18T13:48:30Z"
        results = [subprocess.CompletedProcess([], 0, json.dumps(x).encode(), b"")
                   for x in (first, changed, first)]
        with patch("forecast_provenance_audit.subprocess.run", side_effect=results):
            result = audit(self.proof, **self.options)
        self.assert_held(result)
        self.assertFalse(result["audit_completed"])

    def test_changed_raw_bytes_are_rejected_without_rewriting_any_prediction(self):
        output = json.dumps(self.stdout()).encode()
        def replace_after_cli(*args, **kwargs):
            with (self.proof / "shadow.json").open("ab") as stream:
                stream.write(b"\n")
            return subprocess.CompletedProcess([], 0, output, b"")
        with patch("forecast_provenance_audit.subprocess.run", side_effect=replace_after_cli):
            result = audit(self.proof, **self.options)
        self.assert_held(result)
        self.assertEqual(result["reason"], "PROOF_BYTES_CHANGED_DURING_VERIFICATION")

    def test_valid_cli_zero_pairs_remains_successful_hold(self):
        self.paired.update(comparisons=[], matched_count=0)
        self.slate["point_in_time_market_pairs"] = 0
        self.write_inputs()
        result, _ = self.run_audit()
        self.assert_held(result)
        self.assertTrue(result["audit_completed"])
        self.assertEqual(result["total_pairs"], 0)

    def test_actual_empty_hold_shape_still_requires_all_three_cli_verifications(self):
        # shadow_forecast.build() uses HOLD (not SHADOW_ONLY) for zero predictions.
        self.shadow.update(status="HOLD", predictions=[], predictions_count=0)
        self.paired.update(status="HOLD", comparisons=[], matched_count=0)
        self.slate["point_in_time_market_pairs"] = 0
        self.write_inputs()
        result, run = self.run_audit()
        self.assert_held(result)
        self.assertTrue(result["audit_completed"])
        self.assertTrue(result["signature_identity_and_subjects_verified"])
        self.assertEqual(result["total_pairs"], 0)
        self.assertEqual(result["cases"], [])
        self.assertEqual(run.call_count, 3)
        self.assertFalse(result["eligible_for_betting_promotion"])
        self.assertFalse(result["market_prices_executable"])
        self.assertFalse(result["model_advantage_verified"])

    def test_inconsistent_empty_or_nonempty_hold_documents_are_rejected(self):
        for kind in ("nonempty_hold", "empty_shadow_only", "wrong_count",
                     "empty_with_pair", "empty_paired_research_status"):
            with self.subTest(kind=kind):
                self.shadow.update(status="HOLD", predictions=[], predictions_count=0)
                self.paired.update(status="HOLD", comparisons=[], matched_count=0)
                self.slate["point_in_time_market_pairs"] = 0
                if kind == "nonempty_hold":
                    self.shadow.update(predictions=[self.forecast], predictions_count=1)
                elif kind == "empty_shadow_only": self.shadow["status"] = "SHADOW_ONLY"
                elif kind == "wrong_count": self.shadow["predictions_count"] = 1
                elif kind == "empty_with_pair":
                    self.paired.update(comparisons=[self.pair], matched_count=1)
                    self.slate["point_in_time_market_pairs"] = 1
                elif kind == "empty_paired_research_status": self.paired["status"] = "RESEARCH_ONLY"
                self.write_inputs()
                result, run = self.run_audit()
                self.assert_held(result)
                self.assertFalse(result["audit_completed"])
                run.assert_not_called()

    def test_bad_trusted_args_and_file_boundaries_fail_before_gh(self):
        for options in ({"source_sha": ""}, {"workflow_sha": "bad"}, {"run_id": "../42"},
                        {"attempt": "0"}, {"now": datetime(2026, 10, 18)}):
            with self.subTest(options=options):
                result, run = self.run_audit(**options)
                self.assert_held(result)
                run.assert_not_called()
        with patch("forecast_provenance_audit.MAX_FILE_BYTES", 2):
            result, run = self.run_audit()
        self.assert_held(result)
        run.assert_not_called()
        (self.proof / "shadow.json").unlink()
        (self.proof / "shadow.json").symlink_to(self.proof / "paired.json")
        result, run = self.run_audit()
        self.assert_held(result)
        run.assert_not_called()

    def test_cli_writes_failure_hold_and_uses_nonzero_exit(self):
        output = self.proof.parent / (self.proof.name + "-audit.json")
        self.addCleanup(lambda: output.unlink(missing_ok=True))
        argv = ["--proof", str(self.proof), "--source-sha", SOURCE,
                "--workflow-sha", WORKFLOW_SHA, "--run-id", RUN, "--attempt", "1", "--output", str(output)]
        with patch("forecast_provenance_audit.subprocess.run", side_effect=FileNotFoundError()):
            self.assertEqual(main(argv), 1)
        self.assert_held(json.loads(output.read_text()))

    def test_cli_cannot_overwrite_proof_by_nested_path_or_hardlink_alias(self):
        alias = self.proof.parent / (self.proof.name + "-hardlink.json")
        alias.hardlink_to(self.proof / "shadow.json")
        self.addCleanup(lambda: alias.unlink(missing_ok=True))
        original = (self.proof / "shadow.json").read_bytes()
        for output in (self.proof / "derived" / "audit.json", alias):
            argv = ["--proof", str(self.proof), "--source-sha", SOURCE,
                    "--workflow-sha", WORKFLOW_SHA, "--run-id", RUN, "--attempt", "1",
                    "--output", str(output)]
            with self.subTest(output=output), patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as raised:
                    main(argv)
                self.assertEqual(raised.exception.code, 2)
        self.assertEqual((self.proof / "shadow.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
