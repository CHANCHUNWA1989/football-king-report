"""Offline synthetic commitments to two claimed fixtures; no live signing."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_private_kickoff_crosswalk_gate import sample, source_rows, put_rows
from private_schedule_snapshot_commitment import (
    CommitmentError, make_commitment, replay_commitment, main,
)


def fixture():
    raw, receipt, fixed, market, prediction, seal, sources = sample()
    seal_raw = json.dumps(seal, separators=(",", ":")).encode()
    return raw, receipt, fixed, market, prediction, seal_raw, sources


def create(parts=None):
    parts = fixture() if parts is None else parts
    return make_commitment(*parts)


def replay(parts=None, manifest=None):
    parts = fixture() if parts is None else parts
    manifest = create(parts) if manifest is None else manifest
    return replay_commitment(*parts, manifest)


class PrivateScheduleCommitmentTests(unittest.TestCase):
    def test_commitment_is_private_fixed_fields_and_zero_promotion(self):
        doc = create()
        self.assertEqual(doc["status"], "HOLD")
        self.assertEqual(doc["production_recommendations"], "DISABLED")
        self.assertTrue(doc["private_forecast_seal_and_schedule_structure_replayed"])
        self.assertEqual(doc["sources_checked_as_local_claims"], 2)
        self.assertEqual(doc["certified_independent_forward_samples"], 0)
        for key in (
            "schedule_bytes_externally_attested",
            "publisher_identity_independently_authenticated",
            "publisher_independence_independently_authenticated",
            "claimed_capture_clock_independently_authenticated",
            "real_kickoff_independently_authenticated",
            "quoted_market_prices_independently_authenticated",
            "eligible_for_model_scoring", "eligible_for_betting_promotion",
        ):
            self.assertIs(doc[key], False)
        safe = json.dumps(doc)
        for secret in (
            "Private Home", "Private Away", "OLDB-1", "OPEN-900",
            "openligadb", "openfootball", "1.9183", "1.9587",
            "2026-11-02T08:00:00",
        ):
            self.assertNotIn(secret, safe)

    def test_exact_saved_local_manifest_replays_without_exaggerating_truth(self):
        doc = replay()
        self.assertTrue(doc["local_schedule_manifest_bytes_and_semantics_replayed"])
        self.assertFalse(doc["source_capture_clock_authenticated"])
        self.assertFalse(doc["schedule_bytes_externally_attested"])
        self.assertFalse(doc["actual_kickoff_authenticated"])
        self.assertEqual(doc["status"], "HOLD")
        self.assertEqual(doc["certified_independent_forward_samples"], 0)

    def test_source_descriptor_order_is_canonical(self):
        parts = list(fixture())
        initial = create(parts)
        parts[6] = list(reversed(parts[6]))
        self.assertEqual(initial, create(parts))
        self.assertTrue(replay(parts, initial)["local_schedule_manifest_bytes_and_semantics_replayed"])

    def test_whitespace_only_change_is_detected_even_if_semantics_same(self):
        parts = list(fixture())
        original = create(parts)
        changed = deepcopy(parts)
        rows = source_rows(changed[6][0])
        changed[6][0]["snapshot_bytes"] = json.dumps(rows, indent=2).encode()
        self.assertNotEqual(create(changed), original)
        with self.assertRaisesRegex(CommitmentError, "SCHEDULE_COMMITMENT_REPLAY_MISMATCH"):
            replay(changed, original)

    def test_source_id_capture_clock_and_last_update_changes_reject_replay(self):
        original_parts = fixture()
        original = create(original_parts)
        for mode in ("id", "captured", "updated", "one_raw_byte"):
            with self.subTest(mode=mode):
                parts = deepcopy(original_parts)
                if mode == "id":
                    # A different ID is not the same selected event (fail structural).
                    parts[6][1]["source_event_id"] = "OPEN-901"
                elif mode == "captured":
                    parts[6][1]["captured_utc"] = "2026-11-02T05:00:01Z"
                elif mode == "updated":
                    rows = source_rows(parts[6][1])
                    rows[0]["last_update"] = "2026-11-02T04:58:44Z"
                    put_rows(parts[6][1], rows)
                else:
                    parts[6][1]["snapshot_bytes"] += b" "
                with self.assertRaises(CommitmentError):
                    replay(parts, original)

    def test_wrong_forecast_seal_and_raw_quote_rejected(self):
        parts = list(fixture())
        manifest = create(parts)
        parts[5] += b" "
        with self.assertRaises(CommitmentError):
            replay(parts, manifest)
        parts = list(fixture())
        parts[0] += b" "
        with self.assertRaisesRegex(CommitmentError, "CROSSWALK_OR_SEAL_REPLAY_REJECTED"):
            replay(parts, manifest)
        parts = list(fixture())
        doc = json.loads(parts[5])
        doc["eligible_for_model_scoring"] = True
        parts[5] = json.dumps(doc).encode()
        with self.assertRaisesRegex(CommitmentError, "CROSSWALK_OR_SEAL_REPLAY_REJECTED"):
            replay(parts, manifest)

    def test_wrong_fixture_kickoff_cannot_make_commitment(self):
        parts = list(fixture())
        rows = source_rows(parts[6][1])
        rows[0]["commence_time"] = "2026-11-02T08:00:01Z"
        put_rows(parts[6][1], rows)
        with self.assertRaisesRegex(CommitmentError, "CROSSWALK_OR_SEAL_REPLAY_REJECTED"):
            create(parts)

    def test_missing_second_schedule_source_rejected(self):
        parts = list(fixture())
        parts[6] = [parts[6][0]]
        with self.assertRaises(CommitmentError):
            create(parts)

    def test_fake_verified_bits_and_extra_keys_never_replay(self):
        doc = create()
        for key, value in (
            ("schedule_bytes_externally_attested", True),
            ("publisher_identity_independently_authenticated", True),
            ("claimed_capture_clock_independently_authenticated", True),
            ("real_kickoff_independently_authenticated", True),
            ("certified_independent_forward_samples", 1),
            ("eligible_for_betting_promotion", True),
            ("production_recommendations", "ENABLED"),
            ("schema", "fake-v2"),
            ("malicious_extra", "signed"),
        ):
            with self.subTest(key=key):
                forged = dict(doc, **{key: value})
                with self.assertRaises(CommitmentError):
                    replay(manifest=forged)

    def test_duplicate_semantic_source_and_spoofed_names_fail_closed(self):
        parts = list(fixture())
        parts[6][1] = deepcopy(parts[6][0])
        with self.assertRaises(CommitmentError):
            create(parts)
        parts = list(fixture())
        parts[6][1]["provider_namespace"] = "openligadb"
        with self.assertRaises(CommitmentError):
            create(parts)

    def test_private_cli_new_0600_and_no_overwrite(self):
        raw, receipt, fixture_data, market, prediction, seal_raw, sources = fixture()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = {
                "raw.json": raw, "receipt.json": json.dumps(receipt).encode(),
                "fixture.json": json.dumps(fixture_data).encode(),
                "market.json": json.dumps(market).encode(),
                "prediction.json": prediction, "seal.json": seal_raw,
                "a.json": sources[0]["snapshot_bytes"],
                "b.json": sources[1]["snapshot_bytes"],
            }
            for filename, data in files.items():
                (root/filename).write_bytes(data)
            args = []
            for arg, filename in (
                ("raw-odds", "raw.json"), ("receipt", "receipt.json"),
                ("fixture", "fixture.json"), ("market", "market.json"),
                ("forecast", "prediction.json"), ("seal", "seal.json"),
                ("source-a", "a.json"), ("source-b", "b.json"),
            ):
                args += ["--" + arg, str(root/filename)]
            for i, prefix in enumerate(("source-a", "source-b")):
                args += ["--" + prefix + "-name", sources[i]["provider_namespace"],
                         "--" + prefix + "-id", sources[i]["source_event_id"],
                         "--" + prefix + "-captured-utc", sources[i]["captured_utc"]]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args + ["--output", str(root/"commit.json")]), 0)
            saved = root/"commit.json"
            self.assertEqual(stat.S_IMODE(saved.stat().st_mode), 0o600)
            doc = json.loads(saved.read_text())
            self.assertFalse(doc["schedule_bytes_externally_attested"])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args + ["--verify-commitment", str(saved),
                                            "--output", str(root/"replay.json")]), 0)
            self.assertTrue(json.loads((root/"replay.json").read_text())[
                "local_schedule_manifest_bytes_and_semantics_replayed"])
            self.assertEqual(stat.S_IMODE((root/"replay.json").stat().st_mode), 0o600)
            original = saved.read_bytes()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args + ["--output", str(saved)]), 1)
            self.assertEqual(saved.read_bytes(), original)

    def test_private_manifest_is_not_signed_or_publicly_uploaded(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "private_schedule_snapshot_commitment.py").read_text()
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("requests.get", source)
        self.assertNotIn("gh attestation download", source)
        self.assertIn("real_kickoff_independently_authenticated", source)
        self.assertIn("manifest_sha256_unanchored", source)
        self.assertIn('"HOLD"', source)


if __name__ == "__main__":
    unittest.main()
