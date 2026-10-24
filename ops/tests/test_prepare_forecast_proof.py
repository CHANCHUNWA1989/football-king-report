"""Input-adapter tests; fake bundles are never treated as verified signatures."""
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_forecast_proof as adapter


class PrepareForecastProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.archives = self.base / "forecast_provenance"
        self.archives.mkdir()
        self.output = self.base / "fresh-proof"
        self.raw = {
            "shadow.json": b'{ "predictions": [], "note": "byte preservation" }\n',
            "paired.json": b'{ "comparisons": [] }\n',
            "slate.json": b'{ "rows": [] }\n',
            "research.sigstore.json": b'{ "deliberately_fake_bundle": true }\n',
        }
        self.selected = self.archive("2026/10/19/39405540320-1")
        self.metadata = {
            "id": 39405540320, "run_attempt": 1,
            "repository": {"id": 1411226578,
                           "full_name": "CHANCHUNWA1989/football-king-report"},
            "head_repository": {"id": 1411226578,
                                "full_name": "CHANCHUNWA1989/football-king-report"},
            "head_branch": "main", "path": ".github/workflows/football-king-iphone.yml",
            "status": "completed", "conclusion": "success", "head_sha": "a" * 40,
        }
        self.gh = patch.object(adapter.subprocess, "run").start()
        self.addCleanup(patch.stopall)
        self.gh.return_value = self.response(self.metadata)

    def archive(self, relative):
        target = self.archives / relative
        target.mkdir(parents=True)
        for name, raw in self.raw.items():
            (target / (name + ".gz")).write_bytes(gzip.compress(raw, mtime=0))
        return target

    def response(self, payload, *, returncode=0):
        return SimpleNamespace(returncode=returncode, stdout=json.dumps(payload).encode(),
                               stderr=b"SECRET_CLI_OUTPUT_MUST_NOT_ESCAPE")

    def prepare(self):
        return adapter.prepare(self.archives, self.output)

    def assert_rejected(self, *, before_api=True):
        with self.assertRaises(adapter.PreparationError) as caught:
            self.prepare()
        self.assertRegex(str(caught.exception), r"^[A-Z_]+$")
        self.assertNotIn("SECRET_CLI", str(caught.exception))
        self.assertFalse(self.output.exists())
        if before_api:
            self.gh.assert_not_called()
        else:
            self.gh.assert_called_once()

    def test_four_original_bytes_prepared_using_fresh_metadata(self):
        (self.selected / "shadow.verification.json.gz").write_bytes(b"not even gzip")
        manifest = self.prepare()
        self.assertEqual(manifest, {
            "proof_dir": str(self.output.resolve()), "source_sha": "a" * 40,
            "workflow_sha": "a" * 40, "run_id": "39405540320", "attempt": "1",
            "source_root_relative_ref": "2026/10/19/39405540320-1",
        })
        self.assertEqual(set(p.name for p in self.output.iterdir()),
                         set(self.raw) | {"selection.json"})
        for name, raw in self.raw.items():
            self.assertEqual((self.output / name).read_bytes(), raw)
        self.assertEqual(json.loads((self.output / "selection.json").read_bytes()), manifest)
        self.gh.assert_called_once_with([
            "gh", "api", "repos/CHANCHUNWA1989/football-king-report/actions/runs/39405540320/attempts/1"
        ], capture_output=True, timeout=30, check=False)

    def test_selects_numeric_run_then_attempt_instead_of_date_or_lexical_order(self):
        shutil.rmtree(self.selected)
        self.archive("2026/10/18/9-1")
        self.archive("2026/10/19/10-2")
        newest = self.archive("2026/10/17/10-10")
        for name in self.raw:
            raw = ('{ "selected": "' + name + '" }\n').encode()
            (newest / (name + ".gz")).write_bytes(gzip.compress(raw))
        self.metadata.update(id=10, run_attempt=10)
        self.gh.return_value = self.response(self.metadata)
        result = self.prepare()
        self.assertEqual((result["run_id"], result["attempt"]), ("10", "10"))
        self.assertEqual(result["source_root_relative_ref"], "2026/10/17/10-10")
        self.assertEqual(self.gh.call_args.args[0][-1],
                         "repos/CHANCHUNWA1989/football-king-report/actions/runs/10/attempts/10")
        self.assertIn(b'"selected"', (self.output / "shadow.json").read_bytes())

    def test_latest_missing_or_malformed_input_never_falls_back(self):
        newest = self.archive("2026/10/19/39405540321-1")
        path = newest / "research.sigstore.json.gz"
        original = path.read_bytes()
        for raw in (None, b"not gzip", gzip.compress(b"{broken")):
            with self.subTest(raw=raw):
                path.unlink()
                if raw is not None:
                    path.write_bytes(raw)
                self.assert_rejected()
                if raw is None:
                    path.write_bytes(original)
                self.gh.reset_mock()

    def test_latest_bad_metadata_never_falls_back(self):
        self.archive("2026/10/19/39405540321-1")
        self.assert_rejected(before_api=False)
        self.assertTrue(self.gh.call_args.args[0][-1].endswith("39405540321/attempts/1"))

    def test_invalid_run_identity_types_or_values_rejected(self):
        for key, values in (("id", (True, False, "39405540320", 39405540320.0, 2, None)),
                            ("run_attempt", (True, False, "1", 1.0, 2, None))):
            for value in values:
                with self.subTest(key=key, value=value):
                    metadata = dict(self.metadata, **{key: value})
                    self.gh.return_value = self.response(metadata)
                    self.assert_rejected(before_api=False)
                    self.gh.reset_mock()

    def test_both_repository_ids_and_names_are_strict(self):
        for key in ("repository", "head_repository"):
            examples = (None, [], True, {}, {"id": True, "full_name": adapter.REPOSITORY},
                        {"id": False, "full_name": adapter.REPOSITORY},
                        {"id": str(adapter.REPOSITORY_ID), "full_name": adapter.REPOSITORY},
                        {"id": float(adapter.REPOSITORY_ID), "full_name": adapter.REPOSITORY},
                        {"id": adapter.REPOSITORY_ID, "full_name": "other/fork"},
                        {"id": adapter.REPOSITORY_ID, "full_name": False},
                        {"id": 1, "full_name": adapter.REPOSITORY})
            for value in examples:
                with self.subTest(key=key, value=value):
                    self.gh.return_value = self.response(dict(self.metadata, **{key: value}))
                    self.assert_rejected(before_api=False)
                    self.gh.reset_mock()

    def test_branch_workflow_status_conclusion_and_sha_are_pinned(self):
        examples = {"head_branch": ("dev", None, True),
                    "path": (".github/workflows/other.yml", None),
                    "status": ("in_progress", None),
                    "conclusion": ("failure", "cancelled", None),
                    "head_sha": ("A" * 40, "a" * 39, "a" * 41, "g" * 40, True, None)}
        for key, values in examples.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.gh.return_value = self.response(dict(self.metadata, **{key: value}))
                    self.assert_rejected(before_api=False)
                    self.gh.reset_mock()

    def test_invalid_or_oversized_api_json_is_not_run_metadata(self):
        for raw in (b"", b"[{}]", b"true", b"{broken", b'"text"',
                    b'{"id":1,"id":2}', b'{"id":NaN}', b"x" * 257, "not bytes"):
            with self.subTest(raw=str(raw)[:35]):
                self.gh.return_value = SimpleNamespace(returncode=0, stdout=raw, stderr=b"SECRET")
                with patch.object(adapter, "MAX_API_BYTES", 256):
                    self.assert_rejected(before_api=False)
                self.gh.reset_mock()

    def test_saved_success_reports_never_replace_failed_fresh_api(self):
        for name in ("shadow.verification.json.gz", "paired.verification.json.gz",
                     "slate.verification.json.gz", "negative_checks.json.gz"):
            (self.selected / name).write_bytes(gzip.compress(b'{"verified":true}'))
        self.gh.return_value = self.response(self.metadata, returncode=1)
        self.assert_rejected(before_api=False)

    def test_api_unavailable_and_timeout_reject_without_echoing_output(self):
        for error in (FileNotFoundError("SECRET_CLI_OUTPUT_MUST_NOT_ESCAPE"),
                      subprocess.TimeoutExpired("gh SECRET", 30, output=b"SECRET")):
            with self.subTest(error=type(error).__name__):
                self.gh.side_effect = error
                self.assert_rejected(before_api=False)
                self.gh.reset_mock()

    def test_compressed_size_is_checked_before_decompression_or_api(self):
        path = self.selected / "shadow.json.gz"
        for raw in (b"", b"x" * (adapter.MAX_COMPRESSED_BYTES + 1)):
            with self.subTest(size=len(raw)):
                path.write_bytes(raw)
                self.assert_rejected()

    def test_subject_and_bundle_gzip_bombs_are_bounded(self):
        for name, limit in (("shadow.json", adapter.MAX_SUBJECT_BYTES),
                            ("research.sigstore.json", adapter.MAX_BUNDLE_BYTES)):
            with self.subTest(name=name):
                path = self.selected / (name + ".gz")
                original = path.read_bytes()
                path.write_bytes(gzip.compress(b" " * (limit + 1)))
                self.assertLess(path.stat().st_size, adapter.MAX_COMPRESSED_BYTES)
                self.assert_rejected()
                path.write_bytes(original)

    def test_invalid_decoded_json_and_gzip_are_preflighted_without_api(self):
        path = self.selected / "slate.json.gz"
        for raw in (b"[]", b"null", b"\xff", b"{bad", b'{"a":NaN}', b'{"a":1,"a":2}'):
            with self.subTest(raw=raw):
                path.write_bytes(gzip.compress(raw))
                self.assert_rejected()
        for raw in (b"not gzip", gzip.compress(b"{}")[:-2],
                    b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03\xff\xff\xff"):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                self.assert_rejected()

    def test_nonregular_or_symlink_proof_file_is_rejected(self):
        path = self.selected / "shadow.json.gz"
        path.unlink()
        outside = self.base / "outside.gz"
        outside.write_bytes(gzip.compress(b"{}"))
        path.symlink_to(outside)
        self.assert_rejected()
        path.unlink()
        path.mkdir()
        self.assert_rejected()
        path.rmdir()
        os.mkfifo(path)
        self.assert_rejected()

    def test_archive_root_and_ancestor_symlinks_are_rejected(self):
        alias = self.base / "alias"
        alias.symlink_to(self.archives, target_is_directory=True)
        for root in (alias, alias / "2026", self.base / "missing"):
            with self.subTest(root=root):
                with self.assertRaises(adapter.PreparationError):
                    adapter.prepare(root, self.output)
                self.gh.assert_not_called()
                self.assertFalse(self.output.exists())

    def test_symlink_archive_level_or_latest_candidate_never_falls_back(self):
        outside = self.base / "outside"
        outside.mkdir()
        for relative in ("2025", "2026/09", "2026/10/18", "2026/10/19/39405540321-1"):
            with self.subTest(relative=relative):
                link = self.archives / relative
                link.symlink_to(outside, target_is_directory=True)
                self.assert_rejected()
                link.unlink()

    def test_invalid_archive_date_or_run_path_rejects_before_api(self):
        examples = ("0000/10/18/1-1", "9999/10/18/1-1", "2026/13/18/1-1",
                    "2026/02/30/1-1", "2026/10/00/1-1", "2026/10/32/1-1",
                    "2026/1/18/1-1", "２０２６/10/18/1-1", "2026/１０/18/1-1",
                    "2026/10/18/01-1", "2026/10/18/1-01", "2026/10/18/0-1",
                    "2026/10/18/1-0", "2026/10/18/１-1", "2026/10/18/1-1-extra")
        for relative in examples:
            with self.subTest(relative=relative):
                extra = self.archives / relative
                extra.mkdir(parents=True)
                self.assert_rejected()
                # Remove only the extra path and its now-empty parents.
                while extra != self.archives:
                    try:
                        extra.rmdir()
                    except OSError:
                        break
                    extra = extra.parent

    def test_future_calendar_day_rejected(self):
        with patch.object(adapter, "datetime") as clock:
            from datetime import datetime, timezone
            clock.now.return_value = datetime(2026, 10, 18, 23, 59, tzinfo=timezone.utc)
            self.assert_rejected()

    def test_duplicate_run_attempt_is_ambiguous(self):
        self.archive("2026/10/18/39405540320-1")
        self.assert_rejected()

    def test_entry_bound_counts_parent_directories_too(self):
        self.assertEqual(adapter.MAX_ARCHIVE_ENTRIES, 5000)
        with patch.object(adapter, "MAX_ARCHIVE_ENTRIES", 3):
            self.assert_rejected()

    def test_empty_root_and_unexpected_tree_entries_rejected(self):
        shutil.rmtree(self.selected)
        # Date parents alone are not a usable forecast.
        self.assert_rejected()
        extra = self.archives / "unexpected.txt"
        extra.write_text("not an archive directory")
        self.assert_rejected()

    def test_output_must_be_fresh_and_is_never_overwritten(self):
        self.output.mkdir()
        keep = self.output / "keep.txt"
        keep.write_bytes(b"original")
        with self.assertRaises(adapter.PreparationError):
            self.prepare()
        self.assertEqual(keep.read_bytes(), b"original")
        self.gh.assert_not_called()
        shutil.rmtree(self.output)
        self.output.write_bytes(b"file collision")
        with self.assertRaises(adapter.PreparationError):
            self.prepare()
        self.assertEqual(self.output.read_bytes(), b"file collision")
        self.gh.assert_not_called()

    def test_output_inside_input_or_alias_or_parent_traversal_rejected_before_api(self):
        alias = self.base / "alias"
        alias.symlink_to(self.archives, target_is_directory=True)
        output_alias = self.base / "output-alias"
        output_alias.symlink_to(self.base, target_is_directory=True)
        paths = (self.archives, self.selected / "fresh", alias / "fresh",
                 output_alias / "fresh", self.base / ".." / "fresh")
        for output in paths:
            with self.subTest(output=output):
                with self.assertRaises(adapter.PreparationError):
                    adapter.prepare(self.archives, output)
                self.gh.assert_not_called()
        with self.assertRaises(adapter.PreparationError):
            adapter.prepare(self.archives / ".." / "forecast_provenance", self.output)
        self.gh.assert_not_called()

    def test_double_slash_path_spelling_cannot_alias_output_into_input(self):
        alias_root = Path("/" + str(self.archives))
        self.assertTrue(str(alias_root).startswith("//"))
        with self.assertRaises(adapter.PreparationError):
            adapter.prepare(alias_root, self.archives / "fresh")
        self.gh.assert_not_called()
        self.assertFalse((self.archives / "fresh").exists())

    def test_embedded_nul_path_is_a_safe_rejection(self):
        for root, destination in ((Path(str(self.archives) + "\0bad"), self.output),
                                  (self.archives, Path(str(self.output) + "\0bad"))):
            with self.subTest(root=root, destination=destination):
                with self.assertRaisesRegex(adapter.PreparationError, "^[A-Z_]+$"):
                    adapter.prepare(root, destination)
                self.gh.assert_not_called()

    def test_output_created_during_api_call_is_not_overwritten(self):
        def appear(*args, **kwargs):
            self.output.mkdir()
            (self.output / "keep.txt").write_bytes(b"original")
            return self.response(self.metadata)

        self.gh.side_effect = appear
        with self.assertRaisesRegex(adapter.PreparationError, "OUTPUT_DIRECTORY_ALREADY_EXISTS"):
            self.prepare()
        self.assertEqual(list(self.output.iterdir()), [self.output / "keep.txt"])
        self.assertEqual((self.output / "keep.txt").read_bytes(), b"original")

    def test_output_open_failure_removes_new_empty_directory(self):
        real_open = adapter.os.open

        def reject_output(path, flags, *args, **kwargs):
            if path == self.output.name and flags == adapter.DIRECTORY_FLAGS:
                raise PermissionError("SECRET simulated failure")
            return real_open(path, flags, *args, **kwargs)

        with patch.object(adapter.os, "open", side_effect=reject_output):
            self.assert_rejected(before_api=False)

    def test_latest_bytes_and_metadata_do_not_depend_on_older_proof_contents(self):
        older = self.archive("2026/10/19/9-1")
        (older / "shadow.json.gz").write_bytes(b"old corrupt data must not be read")
        before = {path: path.read_bytes() for path in self.selected.iterdir()}
        self.metadata["head_sha"] = "b" * 40
        self.gh.return_value = self.response(self.metadata)
        result = self.prepare()
        self.assertEqual(result["source_sha"], "b" * 40)
        self.assertEqual(result["workflow_sha"], "b" * 40)
        self.assertEqual(before, {path: path.read_bytes() for path in self.selected.iterdir()})

    def test_output_symlink_collision_and_missing_parent_rejected_before_api(self):
        self.output.symlink_to(self.base / "missing", target_is_directory=True)
        with self.assertRaises(adapter.PreparationError):
            self.prepare()
        self.assertTrue(self.output.is_symlink())
        self.gh.assert_not_called()
        self.output.unlink()
        with self.assertRaises(adapter.PreparationError):
            adapter.prepare(self.archives, self.base / "missing" / "fresh")
        self.gh.assert_not_called()

    def pinned_options(self):
        return {"run_id": "39405540320", "attempt": "1", "case_id": "c" * 64,
                "paired_sha256": hashlib.sha256(self.raw["paired.json"]).hexdigest()}

    def pin_case(self):
        self.raw["paired.json"] = json.dumps({
            "comparisons": [{"case_id": "c" * 64}]
        }).encode()
        (self.selected / "paired.json.gz").write_bytes(
            gzip.compress(self.raw["paired.json"]))

    def test_pinned_original_survives_a_newer_forecast_without_that_case(self):
        self.pin_case()
        newest = self.archive("2026/10/20/39405540321-1")
        (newest/"paired.json.gz").write_bytes(gzip.compress(b'{"comparisons":[]}'))
        result = adapter.prepare(self.archives, self.output, **self.pinned_options())
        self.assertEqual(result["run_id"], "39405540320")
        self.assertEqual(result["attempt"], "1")
        self.assertEqual(result["selection_mode"], "PINNED_ORIGINAL_CASE")
        self.assertEqual(result["expected_case_id"], "c" * 64)
        self.assertEqual(result["paired_sha256"], self.pinned_options()["paired_sha256"])
        self.assertEqual((self.output/"paired.json").read_bytes(), self.raw["paired.json"])
        self.gh.assert_called_once()
        self.assertTrue(self.gh.call_args.args[0][-1].endswith("39405540320/attempts/1"))

    def test_pinned_run_or_attempt_missing_cannot_substitute_latest(self):
        self.pin_case()
        for key, value in (("run_id", "39405540319"), ("attempt", "2")):
            with self.subTest(key=key):
                options = {**self.pinned_options(), key: value}
                with self.assertRaisesRegex(adapter.PreparationError,
                                            "PINNED_FORECAST_ARCHIVE_NOT_FOUND"):
                    adapter.prepare(self.archives, self.output, **options)
                self.gh.assert_not_called()
                self.assertFalse(self.output.exists())

    def test_pinned_options_are_all_required_and_strict(self):
        self.pin_case()
        options = self.pinned_options()
        for key in options:
            bad_values = (None, "", True, 1, "../x", "0", "01", "０１")
            for value in bad_values:
                with self.subTest(key=key, value=value):
                    with self.assertRaisesRegex(adapter.PreparationError, "INVALID_FORECAST_PIN"):
                        adapter.prepare(self.archives, self.output,
                                        **{**options, key: value})
                    self.gh.assert_not_called()
                    self.assertFalse(self.output.exists())

    def test_pinned_digest_mismatch_is_rejected_before_api_or_output(self):
        self.pin_case()
        with self.assertRaisesRegex(adapter.PreparationError, "PINNED_PAIRED_DIGEST_MISMATCH"):
            adapter.prepare(self.archives, self.output,
                            **{**self.pinned_options(), "paired_sha256": "0" * 64})
        self.gh.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_pinned_case_missing_duplicate_or_invalid_cohort_is_rejected(self):
        for cohort in ([], [{"case_id": "d" * 64}],
                       [{"case_id": "c" * 64}] * 2, {}, [None]):
            with self.subTest(cohort=cohort):
                self.raw["paired.json"] = json.dumps({"comparisons": cohort}).encode()
                (self.selected/"paired.json.gz").write_bytes(gzip.compress(
                    self.raw["paired.json"]))
                with self.assertRaises(adapter.PreparationError):
                    adapter.prepare(self.archives, self.output, **self.pinned_options())
                self.gh.assert_not_called()
                self.assertFalse(self.output.exists())

    def test_pinned_corrupt_original_or_failed_api_never_uses_other_run(self):
        self.pin_case()
        self.archive("2026/10/20/39405540321-1")
        self.gh.return_value = self.response(self.metadata, returncode=1)
        with self.assertRaisesRegex(adapter.PreparationError, "RUN_METADATA_API_REJECTED"):
            adapter.prepare(self.archives, self.output, **self.pinned_options())
        self.assertFalse(self.output.exists())
        self.gh.reset_mock()
        (self.selected/"shadow.json.gz").write_bytes(b"corrupt")
        with self.assertRaises(adapter.PreparationError):
            adapter.prepare(self.archives, self.output, **self.pinned_options())
        self.gh.assert_not_called()

    def test_pinned_cli_passes_exact_original_identity(self):
        self.pin_case()
        options = self.pinned_options()
        args = ["--archives", str(self.archives), "--output-dir", str(self.output)]
        for key, value in options.items():
            args += ["--"+key.replace("_", "-"), value]
        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(adapter.main(args), 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["selection_mode"], "PINNED_ORIGINAL_CASE")
        self.assertEqual(result["run_id"], options["run_id"])

    def test_cli_stdout_is_only_safe_selection_json(self):
        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(adapter.main(["--archives", str(self.archives),
                                           "--output-dir", str(self.output)]), 0)
        selection = json.loads(stdout.getvalue())
        self.assertEqual(selection["proof_dir"], str(self.output.resolve()))
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)

    def test_cli_failed_api_or_arguments_emit_safe_hold_json_without_stderr(self):
        self.gh.return_value = SimpleNamespace(returncode=1, stdout=b"SECRET", stderr=b"SECRET")
        for arguments in (["--archives", str(self.archives), "--output-dir", str(self.output)], []):
            with self.subTest(arguments=arguments):
                with patch("sys.stdout", new_callable=io.StringIO) as stdout, \
                        patch("sys.stderr", new_callable=io.StringIO) as stderr:
                    self.assertEqual(adapter.main(arguments), 1)
                result = json.loads(stdout.getvalue())
                self.assertEqual(result["status"], "HOLD")
                self.assertIs(result["preparation_completed"], False)
                self.assertRegex(result["reason"], r"^[A-Z_]+$")
                self.assertEqual(stderr.getvalue(), "")
                self.assertNotIn("SECRET", stdout.getvalue())
                self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
