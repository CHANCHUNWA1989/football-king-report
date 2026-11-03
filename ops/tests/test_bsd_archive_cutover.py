"""Offline producer/consumer tests for the optional BSD archive cutover."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bsd_archive_reader import FILES, inspect_archive, inspect_history_target, main
from bsd_archive_receipt import receipt
from bsd_free import collect
from bsd_overlay import publish

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 3, 0, tzinfo=timezone.utc)


class BSDArchiveCutoverTests(unittest.TestCase):
    def make_checkout(self, tmp):
        root = Path(tmp) / "bsd-research-archive"
        (root / "sources").mkdir(parents=True)
        return root

    def test_present_research_files_are_untrusted_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            blob = b'{"status":"NOT_CONFIGURED"}\n'
            file_path = root / "sources" / FILES[0]
            file_path.write_bytes(blob)
            result = inspect_archive(root)
            self.assertEqual(result["files"][FILES[0]],
                             "PRESENT_UNTRUSTED_UNTIL_VENDOR_VALIDATED")
            self.assertEqual(result["files"][FILES[1]], "MISSING_OPTIONAL")
            self.assertFalse(result["archive_immutable"])
            self.assertFalse(result["source_authenticity_independently_verified"])
            self.assertEqual(result["production_recommendations"], "DISABLED")
            self.assertEqual(file_path.read_bytes(), blob)

    def test_symlinked_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            target = Path(tmp) / "outside.txt"
            target.write_text("do not read me", encoding="utf-8")
            (root / "sources" / FILES[0]).symlink_to(target)
            with self.assertRaisesRegex(ValueError, "NONREGULAR"):
                inspect_archive(root)
            self.assertEqual(target.read_text(encoding="utf-8"), "do not read me")

    def test_oversize_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            (root / "sources" / FILES[0]).write_bytes(b"x" * (1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, "OVERSIZE"):
                inspect_archive(root)

    def test_symlinked_checkout_source_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bsd-research-archive"
            root.mkdir()
            outside = Path(tmp) / "other"
            outside.mkdir()
            (root / "sources").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "DIRECTORY_UNSAFE"):
                inspect_archive(root)

    def test_missing_checkout_cli_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["--root", str(Path(tmp) / "missing")])
            self.assertEqual(rc, 2)
            obj = json.loads(out.getvalue())
            self.assertEqual(obj["status"], "HOLD")
            self.assertEqual(obj["production_recommendations"], "DISABLED")

    def test_optional_missing_market_research_stays_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            site = Path(tmp) / "site"
            site.mkdir()
            (site / "shadow.json").write_text(
                json.dumps({"status": "SHADOW_ONLY", "predictions": [],
                            "production_recommendations": "DISABLED"}),
                encoding="utf-8",
            )
            (root / "sources" / FILES[0]).write_text(
                json.dumps(collect(now=NOW, token="")), encoding="utf-8")
            self.assertEqual(inspect_archive(root)["files"][FILES[1]],
                             "MISSING_OPTIONAL")
            result = publish(
                site, str(root / "sources" / FILES[1]),
                str(root / "sources" / FILES[0]))
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["source_state"], "NOT_CONFIGURED")
            self.assertEqual(result["time_valid_shadow_pairs"], 0)
            self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_workflow_writes_only_to_pinned_archive_branch(self):
        text = (ROOT / ".github/workflows/football-king-bsd-free.yml").read_text(
            encoding="utf-8")
        segment = text.split("\n  archive:\n", 1)[1].split(
            "\n  report_failure:\n", 1)[0]
        self.assertIn("BSD_ARCHIVE_REF: archive/bsd-free-research-v1", segment)
        self.assertIn("ref: archive/bsd-free-research-v1", segment)
        self.assertIn("path: bsd-write-archive", segment)
        self.assertIn("sparse-checkout-cone-mode: false", segment)
        self.assertIn("git -C \"$archive_dir\" fetch", segment)
        self.assertIn('push origin "HEAD:refs/heads/$BSD_ARCHIVE_REF"', segment)
        self.assertIn("BSD_ARCHIVE_FF_PUSH_FAILED", segment)
        self.assertNotIn("refs/heads/main", segment)
        self.assertNotIn("gh api -X PUT", segment)
        self.assertNotIn("--force", segment)

    def test_invalid_archive_checkout_is_quarantined_and_optional_hold(self):
        """An unsafe checked-out optional data path must not abort Pages."""
        text = (ROOT / ".github/workflows/football-king-iphone.yml").read_text(
            encoding="utf-8"
        )
        preflight = text.split(
            "      - name: Refuse unsafe BSD data paths without affecting source forecasts\n",
            1
        )[1].split("\n      - name:", 1)[0]
        self.assertIn("id: bsd_path_preflight", preflight)
        self.assertIn("continue-on-error: true", preflight)
        self.assertIn("python ops/bsd_archive_reader.py --root bsd-research-archive", preflight)
        quarantine = text.split(
            "      - name: Quarantine failed BSD archive path safety check\n",
            1
        )[1].split("\n      - name:", 1)[0]
        self.assertIn("steps.bsd_path_preflight.outcome == 'failure'", quarantine)
        self.assertIn("rm -rf -- bsd-research-archive", quarantine)
        self.assertIn("BSD_ARCHIVE_PREFLIGHT_INVALID_OPTIONAL_HOLD", quarantine)
        self.assertLess(
            text.index("      - name: Quarantine failed BSD archive path safety check"),
            text.index("      - name: Add isolated BSD free-consensus"),
        )
        # Real unsafe checkout structure, then same quarantine-to-HOLD
        # state as workflow; primary site files must remain untouched.
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            outside = Path(tmp) / "outside-status.json"
            outside.write_text('{"do_not_trust": true}', encoding="utf-8")
            (root / "sources" / FILES[0]).symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "NONREGULAR"):
                inspect_archive(root)
            site = self.make_site(tmp, datetime.now(timezone.utc))
            shadow_before = (site / "shadow.json").read_bytes()
            shutil.rmtree(root)
            result = publish(
                site, str(root / "sources" / FILES[1]),
                str(root / "sources" / FILES[0]),
            )
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["reason"], "MISSING_OR_INVALID_BSD_STATUS")
            self.assertEqual(result["production_recommendations"], "DISABLED")
            self.assertEqual(result["time_valid_shadow_pairs"], 0)
            self.assertFalse(result["market_is_executable"])
            self.assertEqual((site / "shadow.json").read_bytes(), shadow_before)
            self.assertTrue((site / "bsd_backup.json").is_file())
            self.assertTrue(outside.is_file())

    def test_iphone_workflow_reads_separate_branch_and_never_main_bsd(self):
        text = (ROOT / ".github/workflows/football-king-iphone.yml").read_text(
            encoding="utf-8")
        self.assertIn("ref: archive/bsd-free-research-v1", text)
        self.assertIn("path: bsd-research-archive", text)
        self.assertIn("sparse-checkout-cone-mode: false", text)
        self.assertIn("id: bsd_archive_checkout", text)
        self.assertIn("continue-on-error: true", text)
        self.assertIn("BSD_ARCHIVE_CHECKOUT_FAILED_OPTIONAL_HOLD", text)
        self.assertIn("if: ${{ steps.bsd_archive_checkout.outcome != 'success' }}", text)
        self.assertIn("if: ${{ steps.bsd_archive_checkout.outcome == 'success' }}", text)
        self.assertIn("rm -rf -- bsd-research-archive", text)
        self.assertIn("python ops/bsd_archive_reader.py --root bsd-research-archive", text)
        self.assertIn(
            "--input bsd-research-archive/sources/bsd_market_latest.json "
            "--status bsd-research-archive/sources/bsd_status_latest.json", text)
        self.assertNotIn("--input sources/bsd_market_latest.json --status", text)
        self.assertIn("production_recommendations", (ROOT / "ops/bsd_overlay.py").read_text(
            encoding="utf-8"))


    def make_site(self, tmp, now):
        site = Path(tmp) / "site"
        site.mkdir()
        (site / "shadow.json").write_text(json.dumps({
            "status": "SHADOW_ONLY", "as_of_utc": now.isoformat(),
            "production_recommendations": "DISABLED",
            "predictions": [{
                "event_id": "shadow-1", "league": "bundesliga",
                "home": "Bayern Munich", "away": "Dortmund",
                "kickoff_utc": (now + __import__("datetime").timedelta(days=2)).isoformat(),
                "prediction_utc": now.isoformat(),
                "p_home": 0.62, "p_draw": 0.22, "p_away": 0.16,
                "production_recommendations": "DISABLED",
            }],
        }), encoding="utf-8")
        return site

    def make_qualified(self, now):
        from datetime import timedelta
        doc = collect(now=now, token="")
        doc.update({
            "status": "RESEARCH_ONLY", "key_present": True,
            "requests_attempted": 3, "league_count": 1,
            "fixture_count": 1, "market_count": 1,
            "events": [{
                "league": "bundesliga", "source_event_id": "sample-1",
                "home": "Bayern Munich", "away": "Dortmund",
                "kickoff_utc": (now + timedelta(days=2)).isoformat(),
                "market_last_update_utc": (now - timedelta(minutes=25)).isoformat(),
                "oldest_leg_update_utc": (now - timedelta(minutes=25)).isoformat(),
                "p_home": 0.62, "p_draw": 0.22, "p_away": 0.16,
                "market_source": "BSD_FREE_CONSENSUS_ONLY",
                "raw_prices_published": False, "not_executable_odds": True,
            }],
        })
        return doc

    def test_newer_no_comparable_status_revokes_old_market_without_replay(self):
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            site = self.make_site(tmp, now)
            root = self.make_checkout(tmp)
            old_market = self.make_qualified(now - timedelta(hours=1))
            newer_status = collect(now=now, token="")
            newer_status["status"] = "NO_COMPARABLE_MARKET"
            m = root / "sources" / FILES[1]
            s = root / "sources" / FILES[0]
            m.write_text(json.dumps(old_market), encoding="utf-8")
            s.write_text(json.dumps(newer_status), encoding="utf-8")
            result = publish(site, str(m), str(s))
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["source_state"], "NO_COMPARABLE_MARKET")
            self.assertEqual(result["time_valid_shadow_pairs"], 0)
            self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_qualified_status_without_matching_market_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            site = self.make_site(tmp, now)
            root = self.make_checkout(tmp)
            status = root / "sources" / FILES[0]
            market = root / "sources" / FILES[1]
            status.write_text(json.dumps(self.make_qualified(now)), encoding="utf-8")
            result = publish(site, str(market), str(status))
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["reason"], "INCONSISTENT_BSD_ARCHIVE_PAIR")
            self.assertEqual(result["time_valid_shadow_pairs"], 0)

    def test_mismatched_market_and_status_cannot_promote_older_market(self):
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            site = self.make_site(tmp, now)
            root = self.make_checkout(tmp)
            status = root / "sources" / FILES[0]
            market = root / "sources" / FILES[1]
            status.write_text(json.dumps(self.make_qualified(now)), encoding="utf-8")
            market.write_text(json.dumps(self.make_qualified(now-timedelta(hours=1))),
                              encoding="utf-8")
            result = publish(site, str(market), str(status))
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["reason"], "INCONSISTENT_BSD_ARCHIVE_PAIR")
            self.assertFalse(result["market_is_executable"])

    def test_old_market_without_authoritative_status_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            site = self.make_site(tmp, now)
            root = self.make_checkout(tmp)
            status = root / "sources" / FILES[0]
            market = root / "sources" / FILES[1]
            market.write_text(json.dumps(self.make_qualified(now)), encoding="utf-8")
            result = publish(site, str(market), str(status))
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["reason"], "MISSING_OR_INVALID_BSD_STATUS")
            self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_matching_status_and_market_research_remains_possible(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            site = self.make_site(tmp, now)
            root = self.make_checkout(tmp)
            status = root / "sources" / FILES[0]
            market = root / "sources" / FILES[1]
            matching = self.make_qualified(now)
            status.write_text(json.dumps(matching), encoding="utf-8")
            market.write_text(json.dumps(matching), encoding="utf-8")
            result = publish(site, str(market), str(status))
            self.assertEqual(result["source_state"], "RESEARCH_ONLY")
            self.assertNotEqual(result["reason"], "INCONSISTENT_BSD_ARCHIVE_PAIR")
            self.assertEqual(result["production_recommendations"], "DISABLED")
            self.assertFalse(result["market_is_executable"])


    def test_valid_empty_source_directory_checkout_is_optional_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bsd-research-archive"
            root.mkdir()
            manifest = inspect_archive(root)
            self.assertEqual(manifest["files"][FILES[0]], "MISSING_OPTIONAL")
            self.assertEqual(manifest["files"][FILES[1]], "MISSING_OPTIONAL")
            report = receipt(root, now=datetime.now(timezone.utc))
            self.assertEqual(report["status"], "HOLD")
            self.assertEqual(report["reason"], "BSD_STATUS_MISSING_OPTIONAL")
            self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_source_directory_as_file_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bsd-research-archive"
            root.mkdir()
            (root / "sources").write_text("not a directory", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "BSD_ARCHIVE_DIRECTORY_UNSAFE"):
                inspect_archive(root)

    def test_historical_valid_archive_becomes_stale_hold_not_invalid(self):
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            captured = datetime(2026, 10, 9, 10, tzinfo=timezone.utc)
            doc = collect(now=captured, token="")
            (root / "sources" / FILES[0]).write_text(
                json.dumps(doc), encoding="utf-8")
            report = receipt(root, now=captured + timedelta(days=30))
            self.assertEqual(report["status"], "HOLD")
            self.assertEqual(report["reason"], "BSD_STALE_OPTIONAL_HOLD")
            self.assertFalse(report["archive_fresh_for_research"])
            self.assertEqual(report["production_recommendations"], "DISABLED")
            self.assertFalse(report["source_authenticity_independently_verified"])

    def test_future_dated_archive_cannot_claim_valid_research(self):
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            now = datetime.now(timezone.utc)
            doc = collect(now=now + timedelta(minutes=15), token="")
            (root / "sources" / FILES[0]).write_text(
                json.dumps(doc), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "BSD_ARCHIVE_FUTURE_CAPTURE"):
                receipt(root, now=now)

    def test_matching_optional_research_pair_is_not_executable_odds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            now = datetime.now(timezone.utc)
            doc = self.make_qualified(now)
            for name in FILES:
                (root / "sources" / name).write_text(
                    json.dumps(doc), encoding="utf-8")
            report = receipt(root, now=now)
            self.assertEqual(report["status"], "RESEARCH_ONLY")
            self.assertEqual(report["reason"], "BSD_OPTIONAL_RESEARCH_PAIR_MATCHES")
            self.assertFalse(report["market_is_executable"])
            self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_inconsistent_research_pair_is_hold(self):
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            now = datetime.now(timezone.utc)
            (root / "sources" / FILES[0]).write_text(
                json.dumps(self.make_qualified(now)), encoding="utf-8")
            (root / "sources" / FILES[1]).write_text(
                json.dumps(self.make_qualified(now-timedelta(hours=1))),
                encoding="utf-8")
            report = receipt(root, now=now)
            self.assertEqual(report["status"], "HOLD")
            self.assertEqual(report["reason"], "BSD_MISMATCHED_MARKET_COUNTERPART")

    def test_duplicate_status_json_keys_cannot_hide_unsafe_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            now = datetime.now(timezone.utc)
            doc = json.dumps(collect(now=now, token=""))
            corrupted = doc[:-1] + ', "production_recommendations":"ENABLED"}'
            (root / "sources" / FILES[0]).write_text(
                corrupted, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "BSD_ARCHIVE_DUPLICATE_JSON_FIELD"):
                receipt(root, now=now)


    def test_published_hold_records_exact_checkout_commit_without_claiming_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            site = self.make_site(tmp, now)
            root = self.make_checkout(tmp)
            status_file = root / "sources" / FILES[0]
            status_file.write_text(json.dumps(collect(now=now, token="")),
                                   encoding="utf-8")
            pin = "b" * 40
            result = publish(
                site, str(root / "sources" / FILES[1]), str(status_file),
                archive_commit=pin)
            recorded = json.loads((site / "bsd_backup.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(recorded["archive_checkout_commit_sha"], pin)
            self.assertEqual(recorded["archive_checkout_branch"],
                             "archive/bsd-free-research-v1")
            self.assertFalse(recorded["archive_git_commit_independently_attested"])
            self.assertFalse(recorded["archive_immutable"])
            self.assertFalse(recorded["source_authenticity_independently_verified"])
            self.assertEqual(recorded["production_recommendations"], "DISABLED")

    def test_invalid_archive_commit_never_promotes_eligible_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            site = self.make_site(tmp, now)
            root = self.make_checkout(tmp)
            s = root / "sources" / FILES[0]
            m = root / "sources" / FILES[1]
            qualified = self.make_qualified(now)
            s.write_text(json.dumps(qualified), encoding="utf-8")
            m.write_text(json.dumps(qualified), encoding="utf-8")
            result = publish(site, str(m), str(s), archive_commit="../../badsha")
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["reason"], "BSD_ARCHIVE_COMMIT_INVALID")
            self.assertEqual(result["time_valid_shadow_pairs"], 0)
            self.assertFalse(result["compared_to_primary_model"])
            self.assertIsNone(result["archive_checkout_commit_sha"])
            self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_duplicate_vendor_fields_never_published_as_valid_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            site = self.make_site(tmp, now)
            root = self.make_checkout(tmp)
            status_path = root / "sources" / FILES[0]
            doc = json.dumps(collect(now=now, token=""))
            status_path.write_text(
                doc[:-1] + ', "production_recommendations":"ENABLED"}',
                encoding="utf-8")
            result = publish(site, str(root / "sources" / FILES[1]),
                             str(status_path), archive_commit="c" * 40)
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["reason"], "MISSING_OR_INVALID_BSD_STATUS")
            self.assertEqual(result["production_recommendations"], "DISABLED")
            self.assertEqual(result["archive_checkout_commit_sha"], "c" * 40)

    def test_iphone_workflow_carries_checked_out_sha_into_bsd_receipt(self):
        text = (ROOT / ".github/workflows/football-king-iphone.yml").read_text(
            encoding="utf-8")
        self.assertIn("git -C bsd-research-archive rev-parse --verify HEAD", text)
        self.assertIn('bsd_pin=(--archive-commit "$archive_sha")', text)
        self.assertIn("bsd_pin[@]", text)
        self.assertIn("BSD_ARCHIVE_PIN_UNAVAILABLE_OPTIONAL_HOLD", text)


    def test_missing_new_bsd_history_tree_is_safe_to_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            history = "sources/bsd_history/2026/11/03/88800000-1.json.gz"
            self.assertIsNone(inspect_history_target(root, history))

    def test_bsd_history_ancestor_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            outside = Path(tmp) / "unrelated"
            outside.mkdir()
            (root / "sources" / "bsd_history").symlink_to(
                outside, target_is_directory=True)
            history = "sources/bsd_history/2026/11/03/88800000-1.json.gz"
            with self.assertRaisesRegex(ValueError, "BSD_ARCHIVE_HISTORY_PATH_UNSAFE"):
                inspect_history_target(root, history)
            self.assertEqual(list(outside.iterdir()), [])

    def test_bsd_history_path_traversal_and_nonregular_target_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            for path in ("../outside", "/tmp/escape",
                         "sources/bsd_history/../../outside",
                         "sources/bsd_history/2026/11/03/abc-1.json.gz"):
                with self.subTest(path=path):
                    with self.assertRaisesRegex(
                        ValueError, "BSD_ARCHIVE_HISTORY_TARGET_INVALID"):
                        inspect_history_target(root, path)
            target = root / "sources/bsd_history/2026/11/03/88800000-1.json.gz"
            target.parent.mkdir(parents=True)
            target.symlink_to(Path(tmp) / "outside.bin")
            with self.assertRaisesRegex(
                ValueError, "BSD_ARCHIVE_HISTORY_TARGET_NONREGULAR"):
                inspect_history_target(
                    root, "sources/bsd_history/2026/11/03/88800000-1.json.gz")


class BSDArchiveCanaryTriggerCoverageTests(unittest.TestCase):
    """A sensitive BSD source change must not silently skip the read-only canary."""

    def test_producer_consumer_and_evidence_dependencies_trigger_canary(self):
        path = ROOT / ".github/workflows/bsd-archive-readonly-canary.yml"
        workflow = path.read_text(encoding="utf-8")
        self.assertIn("  pull_request:\n", workflow)
        self.assertIn("  workflow_dispatch:\n", workflow)
        on_pr = workflow.split("  pull_request:\n", 1)[1].split(
            "  workflow_dispatch:\n", 1)[0]
        required_paths = (
            ".github/workflows/bsd-archive-readonly-canary.yml",
            ".github/workflows/football-king-bsd-free.yml",
            ".github/workflows/football-king-iphone.yml",
            "ops/bsd_archive_reader.py",
            "ops/bsd_archive_receipt.py",
            "ops/bsd_overlay.py",
            "ops/bsd_guard.py",
            "ops/bsd_free.py",
            "ops/market_pair.py",
            "ops/team_identity.py",
            "ops/tests/test_bsd_archive_cutover.py",
            "ops/tests/test_bsd_archive_shell_execution.py",
            "ops/tests/test_bsd_archive_json_ambiguity.py",
            "ops/tests/test_bsd_archive_target_policy.py",
            "ops/tests/test_bsd_free.py",
        )
        for dependency in required_paths:
            with self.subTest(path=dependency):
                self.assertIn("      - '" + dependency + "'", on_pr)


if __name__ == "__main__":
    unittest.main()
