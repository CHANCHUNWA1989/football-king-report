"""Synthetic-only tests. No live odds, authenticated xG or real football photos."""
import copy
import hashlib
import json
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_forward_private_seal import CandidateSealError, seal_candidate
from test_inplay_hkjc_evidence_binding import sample as bound_sample


NOW = datetime(2026, 11, 23, 5, 30, 0, tzinfo=timezone.utc)


def input_case():
    fixture, observations, quote, screenshot_bytes, manifest, _ = bound_sample()
    fixture['source_raw_order'] = [obs['provider'] for obs in observations]
    seal = json.dumps({
        'fixture': fixture, 'provenance_notice': 'SELF_DECLARED_NOT_ATTESTED'
    }, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return {
        'fixture': fixture, 'observations': observations, 'quote': quote,
        'screenshot_bytes': screenshot_bytes, 'screenshot_manifest': manifest,
        'source_raw_bytes': {
            'score_primary': b'synthetic_raw_provider_1',
            'score_secondary': b'synthetic_raw_provider_2',
        },
        'quote_raw_bytes': b'synthetic_raw_bookmaker_quote',
        'fixture_seal_bytes': seal, 'now': NOW,
    }


class InplayForwardPrivateSealTests(unittest.TestCase):
    def test_store_raw_exact_bytes_research_only_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            case = input_case()
            result = seal_candidate(**case, destination=directory)
            self.assertEqual(result['status'], 'RESEARCH_ONLY')
            self.assertEqual(result['decision'], 'HOLD')
            self.assertEqual(result['certified_forward_samples'], 0)
            self.assertEqual(result['production_recommendations'], 'DISABLED')
            self.assertFalse(result['positive_ev_verified'])
            self.assertFalse(result['model_scoring_eligible'])
            target = Path(result['private_archive'])
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),
                             result['archive_sha256'])
            with tarfile.open(target, 'r') as archive:
                self.assertEqual([m.name for m in archive.getmembers()], [
                    'fixture_seal.json', 'score_primary.raw', 'score_secondary.raw',
                    'quote.raw', 'screenshot.raw', 'receipt.json'])
                self.assertEqual(archive.extractfile('screenshot.raw').read(),
                                 case['screenshot_bytes'])
                self.assertEqual(archive.extractfile('quote.raw').read(),
                                 case['quote_raw_bytes'])
                receipt = json.load(archive.extractfile('receipt.json'))
                self.assertFalse(receipt['allowed_for_public_repository'])
                self.assertFalse(receipt['external_timestamp_verified'])
                self.assertFalse(receipt['source_raw_bytes_parsed_or_authenticated'])
                self.assertFalse(receipt['market_executable_verified'])
                self.assertEqual(receipt['certified_forward_samples'], 0)
            self.assertNotIn('2.31', json.dumps(result))

    def test_rewrite_exact_same_second_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            first = seal_candidate(**c, destination=directory)
            prev = Path(first['private_archive']).read_bytes()
            with self.assertRaisesRegex(CandidateSealError, 'IMMUTABLE_CANDIDATE_COLLISION'):
                seal_candidate(**c, destination=directory)
            self.assertEqual(Path(first['private_archive']).read_bytes(), prev)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_changed_image_bytes_without_updated_manifest_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            c['screenshot_bytes'] += b'altered'
            with self.assertRaisesRegex(CandidateSealError, 'INPLAY_CROSS_SOURCE_GATE_HOLD'):
                seal_candidate(**c, destination=directory)
            self.assertFalse(list(Path(directory).iterdir()))

    def test_cross_source_score_conflict_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            c['observations'][1]['score_away'] = 1
            with self.assertRaises(CandidateSealError):
                seal_candidate(**c, destination=directory)

    def test_stale_upstream_quote_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            c['quote']['upstream_updated_utc'] = '2026-11-23T05:26:00Z'
            with self.assertRaises(CandidateSealError):
                seal_candidate(**c, destination=directory)

    def test_prematch_placeholder_stays_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            for obs in c['observations']:
                obs['match_status'] = 'NOT_STARTED'
            with self.assertRaises(CandidateSealError):
                seal_candidate(**c, destination=directory)

    def test_future_result_injection_stays_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            c['quote']['final_score'] = [0, 2]
            with self.assertRaises(CandidateSealError):
                seal_candidate(**c, destination=directory)

    def test_cannot_fake_prematch_fixture_seal_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            c['fixture_seal_bytes'] = c['fixture_seal_bytes'].replace(
                b'SELF_DECLARED_NOT_ATTESTED', b'OFFICIALLY_VERIFIED')
            with self.assertRaises(CandidateSealError):
                seal_candidate(**c, destination=directory)

    def test_duplicate_json_key_in_fixture_seal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            c['fixture_seal_bytes'] = (
                b'{"fixture":{},"fixture":{},"provenance_notice":"SELF_DECLARED_NOT_ATTESTED"}')
            with self.assertRaises(CandidateSealError):
                seal_candidate(**c, destination=directory)

    def test_missing_raw_provider_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            c['source_raw_bytes'].pop('score_secondary')
            with self.assertRaisesRegex(CandidateSealError, 'MISSING_RAW_SCORE_OR_DUPLICATE'):
                seal_candidate(**c, destination=directory)

    def test_wrong_raw_provider_order_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            c['fixture']['source_raw_order'] = ['sofascore', 'fotmob']
            with self.assertRaises(CandidateSealError):
                seal_candidate(**c, destination=directory)

    def test_zero_size_or_oversized_quote_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in (b'', b'x' * 1_000_001):
                c = input_case()
                c['quote_raw_bytes'] = value
                with self.assertRaises(CandidateSealError):
                    seal_candidate(**c, destination=directory)

    def test_missing_private_dir_rejected_and_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'nonexistent'
            with self.assertRaises(CandidateSealError):
                seal_candidate(**input_case(), destination=target)
            self.assertFalse(target.exists())

    def test_symlink_private_dir_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'private'
            original.mkdir()
            alias = Path(directory) / 'alias'
            alias.symlink_to(original, target_is_directory=True)
            with self.assertRaises(CandidateSealError):
                seal_candidate(**input_case(), destination=alias)
            self.assertFalse(list(original.iterdir()))

    def test_git_repository_raw_archive_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / '.git').mkdir()
            with self.assertRaisesRegex(CandidateSealError, 'GIT_WORKTREE_RAW_ARCHIVE_FORBIDDEN'):
                seal_candidate(**input_case(), destination=directory)

    def test_no_input_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            copy_before = copy.deepcopy(c)
            seal_candidate(**c, destination=directory)
            self.assertEqual(c, copy_before)

    def test_finished_game_cannot_be_backdated_by_local_now(self):
        with tempfile.TemporaryDirectory() as directory:
            c = input_case()
            c['now'] = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
            with self.assertRaises(CandidateSealError):
                seal_candidate(**c, destination=directory)


if __name__ == '__main__':
    unittest.main()
