import json
import unittest
from intelligence_x_rehearsal import MAX_INPUT, decode, replay


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.registry = {s: dict(publisher_group='p'+s, origin_group='o'+s, provider_fixture_id=s)
                         for s in ('a', 'b')}
        a = dict(source='a', fixture_id='m', provider_fixture_id='a', phase='SECOND_HALF',
                 home_score=1, away_score=0, home_red_cards=0, away_red_cards=1,
                 updated_at='2026-11-24T13:49:00Z', observed_at='2026-11-24T13:49:20Z',
                 payload_sha256='a'*64)
        self.batch = {'kind': 'SNAPSHOTS', 'snapshots': [a, dict(a, source='b', provider_fixture_id='b', payload_sha256='b'*64)]}
        self.outage = {'kind': 'UNAVAILABLE'}

    def req(self, attempts):
        return dict(fixture_id='m', registry=self.registry, now_utc='2026-11-24T13:50:00Z', attempts=attempts)

    def test_real_p25_agreement(self):
        out = replay(self.req([self.batch]))
        self.assertEqual(out['diagnostic'], 'AGREEMENT_CANDIDATE')
        self.assertEqual(out['status'], 'HOLD')
        self.assertIs(out['eligible_for_model_scoring'], False)
        self.assertNotIn('match_state', out)
        self.assertNotIn('fixture_id', out)

    def test_outage_then_candidate(self):
        for n in (1, 2):
            out = replay(self.req([self.outage]*n + [self.batch]))
            self.assertEqual((out['attempts'], out['unavailable_attempts'], out['diagnostic']), (n+1, n, 'AGREEMENT_CANDIDATE'))

    def test_total_outage(self):
        for n in (1, 2, 3):
            out = replay(self.req([self.outage]*n))
            self.assertEqual((out['attempts'], out['unavailable_attempts'], out['diagnostic']), (n, n, 'UNAVAILABLE'))

    def test_conflicting_data_cannot_be_retried(self):
        self.batch['snapshots'][1]['home_score'] = 0
        self.assertEqual(replay(self.req([self.outage, self.batch]))['diagnostic'], 'BLOCKED')
        with self.assertRaises(ValueError):
            replay(self.req([self.batch, self.outage]))

    def test_no_cherry_picking(self):
        with self.assertRaises(ValueError):
            replay(self.req([self.batch, self.batch]))

    def test_invalid_sequence(self):
        for rows in ([], [self.outage]*4, [{'kind': 'UNAVAILABLE', 'raw': 'x'}], [None]):
            with self.assertRaises(ValueError):
                replay(self.req(rows))

    def test_invalid_registry_during_outage(self):
        self.registry.clear()
        with self.assertRaises(ValueError):
            replay(self.req([self.outage]))

    def test_bounded_json_and_duplicate_keys(self):
        for raw in (b'', b' '* (MAX_INPUT+1), b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff'):
            with self.assertRaises(ValueError):
                decode(raw)
        req = self.req([self.outage, self.batch])
        self.assertEqual(replay(decode(json.dumps(req).encode())), replay(req))

    def test_old_data_remains_blocked(self):
        self.batch['snapshots'][0]['updated_at'] = '2026-11-24T13:40:00Z'
        self.assertEqual(replay(self.req([self.outage, self.batch]))['diagnostic'], 'BLOCKED')

    def test_extra_request_fields_rejected(self):
        with self.assertRaises(ValueError):
            replay(dict(self.req([self.outage]), live_execution_allowed=True))


if __name__ == '__main__':
    unittest.main()
