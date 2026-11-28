import hashlib
import json
import unittest

from ops.forward_forecast_binding import audit_bindings


def sample():
    row = dict(league='epl', event_id='id-1', home='A', away='B',
               kickoff_utc='2026-11-28T15:00:00Z', prediction_utc='2026-11-28T14:00:00Z')
    return row


def encode(rows):
    raw = json.dumps({'predictions': rows, 'predictions_count': len(rows)}).encode()
    return raw, hashlib.sha256(raw).hexdigest()


class BindingTests(unittest.TestCase):
    def test_exact_row_is_bound_not_certified(self):
        row = sample()
        raw, digest = encode([row])
        result = audit_bindings(raw, digest, [row])
        self.assertEqual(result['rows'][0]['reason'], 'EXACT_ARCHIVED_ROW')
        self.assertEqual(result['bound_count'], 1)
        self.assertEqual(result['authenticated_samples'], 0)
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['production_recommendations'], 'DISABLED')

    def test_wrong_archive_digest(self):
        raw, digest = encode([sample()])
        self.assertEqual(audit_bindings(raw + b' ', digest, [sample()])['archive_reason'], 'ARCHIVE_DIGEST_MISMATCH')

    def test_forged_fixture(self):
        row = sample()
        raw, digest = encode([row])
        for field in ('league', 'event_id', 'home', 'away', 'kickoff_utc', 'prediction_utc'):
            with self.subTest(field=field):
                forged = dict(row, **{field: 'wrong'})
                self.assertEqual(audit_bindings(raw, digest, [forged])['bound_count'], 0)

    def test_duplicate_event_id_quarantines_archive(self):
        row = sample()
        raw, digest = encode([row, dict(row, away='C')])
        self.assertEqual(audit_bindings(raw, digest, [row])['archive_reason'], 'AMBIGUOUS_ARCHIVE_IDENTITY')

    def test_duplicate_fixture_different_ids(self):
        row = sample()
        raw, digest = encode([row, dict(row, event_id='id-2')])
        self.assertEqual(audit_bindings(raw, digest, [row])['archive_reason'], 'AMBIGUOUS_ARCHIVE_IDENTITY')

    def test_duplicate_claims(self):
        row = sample()
        raw, digest = encode([row])
        self.assertEqual(audit_bindings(raw, digest, [row, row])['bound_count'], 0)

    def test_invalid_json_duplicates_and_nonfinite(self):
        for raw in (b'{"predictions":[],"predictions":[],"predictions_count":0}', b'{"predictions":[],"predictions_count":NaN}'):
            self.assertEqual(audit_bindings(raw, hashlib.sha256(raw).hexdigest(), [])['archive_reason'], 'INVALID_ARCHIVE')

    def test_invalid_clock_or_leakage(self):
        for clock in ('2026-11-28T15:00:00Z', '2026-11-28T14:00:00', 'bad'):
            row = dict(sample(), prediction_utc=clock)
            raw, digest = encode([row])
            self.assertEqual(audit_bindings(raw, digest, [row])['archive_reason'], 'INVALID_ARCHIVE_ROW')

    def test_declared_count_mismatch(self):
        raw = b'{"predictions":[],"predictions_count":1}'
        self.assertEqual(audit_bindings(raw, hashlib.sha256(raw).hexdigest(), [])['archive_reason'], 'INVALID_ARCHIVE')

    def test_missing_row(self):
        raw, digest = encode([])
        self.assertEqual(audit_bindings(raw, digest, [sample()])['rows'][0]['reason'], 'NO_EXACT_ARCHIVED_ROW')

    def test_malformed_claim(self):
        raw, digest = encode([sample()])
        self.assertEqual(audit_bindings(raw, digest, [None])['rows'][0]['reason'], 'INVALID_CLAIM')


if __name__ == '__main__':
    unittest.main()
