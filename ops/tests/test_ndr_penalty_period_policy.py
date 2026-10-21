"""Versioned ordinary-penalty observations never authenticate football results.

The archived fixture is original input only; this test is not a fresh signature
verification, an independently certified outcome, or a backfilled old report.
"""
import gzip
import hashlib
import io
from pathlib import Path
import tarfile
import unittest

from ops import ndr_completion_observations as observations
from ops.ndr_result_observations import parse_html
from ops.tests import test_ndr_completion_observations as fixture


LEGACY = 'NDR_COMPLETION_DISPLAY_V1'
MODERN = 'NDR_REGULATION_EVENT_ICONS_V2'
PREFIX = '/resources/assets/resources/images/svg/icons/'
GOAL = PREFIX + 'sport-ticker-goal-penalty-football.svg'
MISSED = PREFIX + 'sport-ticker-penalty-missed-football.svg'
GOAL_ALT = 'Tor durch Strafstoß (Elfmeter/Penalty/7-Meter etc.)'
MISSED_ALT = 'Strafstoß verschossen (Elfmeter/Penalty/7-Meter etc.)'


def ordinary(*, missed=False, clock='76. Min.', icon=None, alt=None):
    return fixture.tick(clock=clock, label='Elfmeter verschossen' if missed else 'Tor durch Strafstoß',
                        icon=(MISSED if missed else GOAL) if icon is None else icon,
                        alt=(MISSED_ALT if missed else GOAL_ALT) if alt is None else alt)


class NDRPenaltyPeriodPolicyTests(unittest.TestCase):
    def modern(self, raw, row=None):
        return observations.parse_detail(raw, fixture.expected() if row is None else row,
                                         policy=MODERN)

    def reject(self, raw, row=None):
        with self.assertRaises(ValueError):
            self.modern(raw, row)

    def held(self, result):
        self.assertEqual(result['parser_policy'], MODERN)
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['production_recommendations'], 'DISABLED')
        self.assertTrue(result['candidate_only'])
        for key in ['completion_authenticated', 'period_authenticated',
                    'independently_verified', 'eligible_for_model_scoring']:
            self.assertIs(result[key], False, key)
        for key in ['score_ft', 'ft', 'y', 'kickoff_utc', 'result_verified']:
            self.assertNotIn(key, result)

    def test_original_5988_raw_passes_only_explicit_modern_observation_policy(self):
        path = (Path(__file__).resolve().parents[2] /
                'ndr_capture_provenance/2026/10/21/39534272252-1/ndr-capture.tar.gz')
        with gzip.open(path, 'rb') as stream:
            capture = stream.read(16_000_001)
        self.assertLessEqual(len(capture), 16_000_000)
        with tarfile.open(fileobj=io.BytesIO(capture), mode='r:') as archive:
            files = {}
            for name in ['ndr.html', 'ndr-detail-5988.html']:
                member = archive.getmember(name)
                self.assertTrue(member.isreg())
                self.assertLessEqual(member.size, 3_000_000)
                with archive.extractfile(member) as stream:
                    files[name] = stream.read(3_000_001)
                self.assertEqual(len(files[name]), member.size)
        raw = files['ndr-detail-5988.html']
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '1d6af817ecf2c48700056d2c2d4d43e75fdef755cc77b3e7554cdaed124e0b0b')
        row = next(item for item in parse_html(files['ndr.html'])[0]
                   if item['provider_fixture_id'] == '5988')
        with self.assertRaisesRegex(ValueError, 'NON_REGULATION_NDR_EVENT_MARKER'):
            observations.parse_detail(raw, row)
        with self.assertRaisesRegex(ValueError, 'NON_REGULATION_NDR_EVENT_MARKER'):
            observations.parse_detail(raw, row, policy=LEGACY)
        result = self.modern(raw, row)
        self.held(result)
        self.assertEqual(result['provider_fixture_id'], '5988')
        self.assertEqual(result['end_event_clock'], {'base_minute': 90, 'stoppage_minute': 10})
        self.assertEqual(result['display_score'], {'home': 4, 'away': 3})

    def test_exact_ordinary_goal_and_missed_icons_are_observations(self):
        for extra in [ordinary(), ordinary(missed=True, clock='4. Min.'),
                      ordinary(missed=True, clock='90.<span>+4</span> Min.')]:
            with self.subTest(extra=extra):
                raw = fixture.detail(fixture.tick() + extra)
                with self.assertRaisesRegex(ValueError, 'NON_REGULATION_NDR_EVENT_MARKER'):
                    observations.parse_detail(raw, fixture.expected())
                self.held(self.modern(raw))

    def test_default_and_explicit_legacy_output_remain_exact(self):
        plain = fixture.detail()
        before = observations.parse_detail(plain, fixture.expected())
        self.assertEqual(before, observations.parse_detail(plain, fixture.expected(), policy=LEGACY))
        self.assertNotIn('parser_policy', before)
        modern = self.modern(plain)
        self.held(modern)
        self.assertEqual({k: v for k, v in modern.items() if k != 'parser_policy'}, before)

    def test_unknown_policy_cannot_request_a_permissive_parser(self):
        for policy in [None, True, 2, '', MODERN.lower(), MODERN + '_UNKNOWN', [], {}]:
            with self.subTest(policy=policy), self.assertRaisesRegex(ValueError, 'INVALID_NDR_COMPLETION_PARSER_POLICY'):
                observations.parse_detail(fixture.detail(), fixture.expected(), policy=policy)

    def test_exact_pair_is_required_and_unknown_penalty_markers_stay_rejected(self):
        for icon, alt in [(GOAL, MISSED_ALT), (MISSED, GOAL_ALT), (GOAL, 'Penalty'),
                          (GOAL, GOAL_ALT + ' '), (GOAL + '?x=1', GOAL_ALT),
                          ('https://www.ndr.de' + GOAL, GOAL_ALT),
                          ('/penalty.svg', 'Penalty'), (GOAL, 'Penalties'),
                          (GOAL, 'Elfmeterschießen')]:
            with self.subTest(icon=icon, alt=alt):
                self.reject(fixture.detail(fixture.tick() + ordinary(icon=icon, alt=alt)))

    def test_ordinary_icon_must_belong_to_own_event_subhead(self):
        event = ordinary()
        icon_start = '<img class="incident-icon"'
        img = event[event.index(icon_start):event.index('>', event.index(icon_start)) + 1]
        outside = fixture.detail().replace(b'</article>', img.encode() + b'</article>')
        wrong_scope = event.replace(img, '').replace('<div class="liveticker-headline">',
                                                    '<div class="liveticker-headline">' + img)
        wrapped = event.replace(img, '<span>' + img + '</span>')
        missing_class = event.replace('class="incident-icon"', 'class="unrelated"')
        duplicate = event.replace(img, img + img)
        duplicate_subhead = event.replace('</li>', '<div class="liveticker-subhead"></div></li>')
        for raw in [outside] + [fixture.detail(fixture.tick() + one) for one in
                               [wrong_scope, wrapped, missing_class, duplicate, duplicate_subhead]]:
            with self.subTest(raw=raw):
                self.reject(raw)

    def test_hidden_or_unscoped_penalty_clock_never_qualifies_for_exception(self):
        event = ordinary()
        for one in [event.replace('class="incident-icon"', 'class="incident-icon" hidden'),
                    event.replace('class="liveticker-subhead"', 'class="liveticker-subhead" hidden'),
                    event.replace('class="liveticker-item"', 'class="liveticker-item" aria-hidden="true"'),
                    event.replace('class="liveticker-time theta"', 'class="unrelated"'),
                    event.replace('<div class="liveticker-time theta">76. Min.</div>', ''),
                    event.replace('</li>', '<div class="liveticker-time">76. Min.</div></li>'),
                    event.replace('<div class="liveticker-time theta">76. Min.</div>',
                                  '<span><div class="liveticker-time theta">76. Min.</div></span>')]:
            with self.subTest(one=one):
                self.reject(fixture.detail(fixture.tick() + one))

    def test_ordinary_icon_subhead_contains_only_the_icon_and_whitespace(self):
        for text in ['Elfmeterschießen', 'Verlängerung', 'Penalties', 'Other']:
            event = ordinary().replace('<div class="liveticker-subhead">',
                                       '<div class="liveticker-subhead">' + text)
            with self.subTest(text=text):
                self.reject(fixture.detail(fixture.tick() + event))
        self.held(self.modern(fixture.detail(fixture.tick() + ordinary().replace(
            '<div class="liveticker-subhead">', '<div class="liveticker-subhead">\n\t '))))

    def test_normal_icons_do_not_override_extra_time_or_shootout_evidence(self):
        for event in [ordinary(clock='105. Min.'), ordinary(clock='120. Min.'),
                      ordinary(clock='91. Min.'), ordinary(clock='90.<span>+31</span> Min.'),
                      ordinary(clock='90.<span>+6</span> Min.'),
                      ordinary().replace('Tor durch Strafstoß</b>', 'Anpfiff Verlängerung</b>'),
                      ordinary().replace('Tor durch Strafstoß</b>', 'Elfmeterschießen</b>'),
                      ordinary().replace('class="liveticker-item"', 'class="liveticker-item penalties"'),
                      fixture.tick(label='Elfmeterschießen', icon='/other.svg', alt='Elfmeterschießen')]:
            with self.subTest(event=event):
                self.reject(fixture.detail(fixture.tick() + event))

    def test_new_icon_policy_preserves_match_identity_status_score_and_end_guards(self):
        body = fixture.detail(fixture.tick() + ordinary())
        for raw in [body.replace(b'>Ende<', b'>Ende i.E.<'),
                    body.replace(b'mannschaftfussball264', b'mannschaftfussball999'),
                    body.replace(b'finalresult">1:0', b'finalresult">2:0'),
                    body.replace(b'2026-2027', b'2025-2026'),
                    fixture.detail(fixture.tick(clock='120. Min.') + ordinary()),
                    fixture.detail(fixture.tick() + fixture.tick() + ordinary())]:
            with self.subTest(raw=raw):
                self.reject(raw)
