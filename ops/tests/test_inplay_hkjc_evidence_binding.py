"""Synthetic-only tests: no football API, no real HKJC price or attestation."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_hkjc_evidence_binding import audit


IMG = b'FAKE PNG BYTES - SYNTHETIC, NOT A REAL SCREENSHOT'
HASH = hashlib.sha256(IMG).hexdigest()


def sample():
    fixture = {
        'fixture_id': 'research_fixture_1', 'gender': 'women',
        'league': 'japan_we_league', 'home_id': 'synthetic_nagano',
        'away_id': 'synthetic_urawa',
        'kickoff_utc': '2026-11-23T05:00:00Z',
        'expected_identity_sealed_utc': '2026-11-23T04:20:00Z',
        'provider_event_ids': {'fotmob': 'fotmob_111', 'sofascore': 'sofa_222'},
        'provider_event_urls': {
            'fotmob': 'https://www.fotmob.com/matches/synthetic/111',
            'sofascore': 'https://www.sofascore.com/football/match/synthetic/222'},
        'bookmaker_id': 'hkjc', 'bookmaker_event_id': 'FB9427',
        'bookmaker_host': 'bet.hkjc.com',
        'screenshot_labels': {'league': '女子日本職業聯賽',
                              'home': '長野帕塞羅女足', 'away': '浦和紅鑽女足'},
    }
    scores = []
    for provider in ('fotmob', 'sofascore'):
        scores.append({
            'provider': provider,
            'source_event_id': fixture['provider_event_ids'][provider],
            'gender': fixture['gender'], 'league': fixture['league'],
            'home_id': fixture['home_id'], 'away_id': fixture['away_id'],
            'kickoff_utc': fixture['kickoff_utc'],
            'source_url': fixture['provider_event_urls'][provider],
            'captured_utc': '2026-11-23T05:29:53Z',
            'source_updated_utc': '2026-11-23T05:29:50Z',
            'last_material_event_utc': '2026-11-23T05:00:00Z',
            'match_status': 'FIRST_HALF', 'score_home': 0, 'score_away': 0,
            'elapsed_regulation_minutes': 30,
            'home_red_cards': 0, 'away_red_cards': 0,
        })
    quote = {
        'fixture_id': fixture['fixture_id'],
        'bookmaker_event_id': fixture['bookmaker_event_id'],
        'bookmaker_id': fixture['bookmaker_id'],
        'source_url': 'https://bet.hkjc.com/football/synthetic',
        'market': 'HKJC_THREE_WAY_HANDICAP', 'selection': 'AWAY',
        'home_handicap': 1, 'decimal_price': 2.31, 'in_play': True,
        'upstream_updated_utc': '2026-11-23T05:29:55Z',
        'captured_utc': '2026-11-23T05:29:57Z',
        'image_sha256': HASH,
    }
    manifest = {
        'image_sha256': HASH,
        'fixture': {'event_id': 'FB9427', **fixture['screenshot_labels']},
        'screenshot': {'event_id': 'FB9427', 'human_reviewed': True,
                       'observed_at_utc': '2026-11-23T05:29:56Z',
                       'home_goals': 0, 'away_goals': 0, 'minute': 30},
    }
    return fixture, scores, quote, IMG, manifest, '2026-11-23T05:30:00Z'


class PointInTimeEvidenceBindingTests(unittest.TestCase):
    def inspect(self, fixture=None, scores=None, quote=None, image=None, manifest=None, now=None):
        c = sample()
        data = [x if x is not None else default for x, default in zip(
            (fixture, scores, quote, image, manifest, now), c)]
        return audit(*data)

    def test_synthetic_consistent_inputs_are_research_only_and_still_hold(self):
        a = self.inspect()
        self.assertEqual(a['status'], 'RESEARCH_ONLY')
        self.assertTrue(a['structure_consistent'])
        self.assertEqual(a['decision'], 'HOLD')
        self.assertEqual(a['production_recommendations'], 'DISABLED')
        self.assertEqual(a['candidate_manifest']['claimed_decimal_price'], 2.31)
        self.assertEqual(len(a['candidate_manifest']['sha256_self_declared_not_attested']), 64)
        for key in ('independent_sources_authenticated', 'screenshot_content_verified',
                    'quote_matches_image_verified', 'bookmaker_price_executable_verified',
                    'point_in_time_externally_attested', 'model_scoring_eligible',
                    'positive_ev_verified', 'probabilities_calibrated'):
            self.assertFalse(a[key], key)
        self.assertIsNone(a['recommendation'])
        self.assertIsNone(a['stakes'])

    def test_mismatched_quote_event_id_holds(self):
        f, s, q, i, m, n = sample()
        q['bookmaker_event_id'] = 'OTHER'
        self.assertEqual(self.inspect(f,s,q,i,m,n)['status'], 'HOLD')

    def test_duplicate_source_publisher_holds(self):
        f, s, q, i, m, n = sample()
        s[1] = copy.deepcopy(s[0])
        self.assertEqual(self.inspect(f,s,q,i,m,n)['status'], 'HOLD')

    def test_conflicting_score_claims_hold(self):
        f, s, q, i, m, n = sample()
        s[1]['score_away'] = 1
        self.assertEqual(self.inspect(f,s,q,i,m,n)['status'], 'HOLD')

    def test_prematch_zero_placeholder_cannot_pass_live_gate(self):
        f, s, q, i, m, n = sample()
        for obs in s:
            obs['match_status'] = 'NOT_STARTED'
        result = self.inspect(f,s,q,i,m,n)
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['decision'], 'HOLD')
        self.assertIsNone(result['candidate_manifest'])

    def test_finished_score_cannot_masquerade_as_live(self):
        f, s, q, i, m, n = sample()
        for obs in s:
            obs['match_status'] = 'FINISHED'
        self.assertEqual(self.inspect(f,s,q,i,m,n)['status'], 'HOLD')

    def test_image_digest_tampering_holds(self):
        f, s, q, i, m, n = sample()
        self.assertEqual(self.inspect(f,s,q,i+b'!',m,n)['status'], 'HOLD')

    def test_screenshot_score_conflict_holds(self):
        f, s, q, i, m, n = sample()
        m['screenshot']['away_goals'] = 1
        self.assertEqual(self.inspect(f,s,q,i,m,n)['reason'], 'SCREENSHOT_SCORE_CONFLICT')

    def test_screenshot_event_and_display_binding(self):
        f, s, q, i, m, n = sample()
        m['fixture']['event_id'] = 'BAD'
        self.assertEqual(self.inspect(f,s,q,i,m,n)['status'], 'HOLD')
        f, s, q, i, m, n = sample()
        m['fixture']['away'] = 'another club'
        self.assertEqual(self.inspect(f,s,q,i,m,n)['reason'], 'SCREENSHOT_DISPLAY_FIXTURE_CONFLICT')

    def test_missing_real_upstream_market_timestamp_holds(self):
        f, s, q, i, m, n = sample()
        del q['upstream_updated_utc']
        self.assertEqual(self.inspect(f,s,q,i,m,n)['status'], 'HOLD')

    def test_stale_source_claim_holds_despite_fresh_screenshot(self):
        f, s, q, i, m, n = sample()
        s[0]['source_updated_utc'] = '2026-11-23T05:22:00Z'
        self.assertEqual(self.inspect(f,s,q,i,m,n)['status'], 'HOLD')

    def test_quote_older_than_last_goal_event_holds(self):
        f, s, q, i, m, n = sample()
        for obs in s:
            obs['last_material_event_utc'] = '2026-11-23T05:29:56Z'
            obs['source_updated_utc'] = '2026-11-23T05:29:58Z'
            obs['captured_utc'] = '2026-11-23T05:29:59Z'
        self.assertEqual(self.inspect(f,s,q,i,m,n)['reason'], 'STALE_OR_PRE_EVENT_QUOTE')

    def test_quote_not_same_instant_as_screenshot_holds(self):
        f, s, q, i, m, n = sample()
        q['captured_utc'] = '2026-11-23T05:27:40Z'
        q['upstream_updated_utc'] = '2026-11-23T05:27:39Z'
        self.assertEqual(self.inspect(f,s,q,i,m,n)['status'], 'HOLD')

    def test_wrong_market_asians_cannot_be_labeled_hkjc_threeway(self):
        f, s, q, i, m, n = sample()
        q['market'] = 'asian_handicap'
        self.assertEqual(self.inspect(f,s,q,i,m,n)['reason'], 'UNSUPPORTED_THREE_WAY_MARKET')

    def test_noninteger_and_boolean_handicap_rejected(self):
        for line in (True, 0.75, -0.25, 5, -5):
            f, s, q, i, m, n = sample()
            q['home_handicap'] = line
            self.assertEqual(self.inspect(f,s,q,i,m,n)['status'], 'HOLD')

    def test_missing_red_card_evidence_holds(self):
        f, s, q, i, m, n = sample()
        del s[0]['home_red_cards']
        self.assertEqual(self.inspect(f,s,q,i,m,n)['reason'], 'RED_CARD_EVIDENCE_MISSING')

    def test_red_card_effect_unmodelled_holds(self):
        f, s, q, i, m, n = sample()
        s[0]['away_red_cards'] = 1
        self.assertEqual(self.inspect(f,s,q,i,m,n)['reason'], 'RED_CARD_EFFECT_UNMODELLED')

    def test_unpinned_url_source_cannot_claim_bookmaker(self):
        f, s, q, i, m, n = sample()
        q['source_url'] = 'https://bet.hkjc.com.evil.example/path'
        self.assertEqual(self.inspect(f,s,q,i,m,n)['reason'], 'UNBOUND_BOOKMAKER_URL')

    def test_future_result_or_fake_ev_input_rejected(self):
        for key in ('final_score', 'positive_ev_verified', 'model_probability'):
            f, s, q, i, m, n = sample()
            q[key] = [0, 2] if key == 'final_score' else True
            self.assertEqual(self.inspect(f,s,q,i,m,n)['status'], 'HOLD')

    def test_no_input_mutation(self):
        case = sample()
        clone = copy.deepcopy(case)
        self.inspect(*case)
        self.assertEqual(case, clone)

    def test_repeated_receipt_same_inputs_stable_not_external_attestation(self):
        a, b = self.inspect(), self.inspect()
        self.assertEqual(a['candidate_manifest'], b['candidate_manifest'])
        self.assertFalse(a['point_in_time_externally_attested'])


if __name__ == '__main__':
    unittest.main()
