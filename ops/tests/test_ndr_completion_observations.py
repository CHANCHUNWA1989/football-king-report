"""NDR's explicit completion display remains unauthenticated research evidence."""
import copy
import unittest

from ops.ndr_completion_observations import MAX_BYTES, parse_detail
from ops.ndr_result_observations import parse_html
from ops.tests.test_ndr_result_observations import page as row_page, row


URL = 'https://www.ndr.de/sport/ergebnisse/spielstatistik-5884.html'
END_ICON = '/resources/assets/resources/images/svg/icons/sport-ticker-end.svg'
UNSET = object()


def expected():
    return parse_html(row_page(row()))[0][0]


def tick(clock='90.<span>+5</span> Min.', score='1:0', label='Spielende',
         icon=END_ICON, alt='Spielende'):
    return f'''<li class="liveticker-item"><div class="liveticker-time theta">{clock}</div>
<div class="liveticker-headline"><span class="liveticker-headline-score">{score}</span></div>
<div class="liveticker-subhead"><img class="incident-icon" src="{icon}" alt="{alt}"></div>
<div class="liveticker-text small"><b>{label}</b></div></li>'''


def detail(ticks=None):
    return f'''<!DOCTYPE html><html><head><link rel="canonical" href="{URL}">
<meta property="og:url" content="{URL}"></head><body>
<article class="page-sport-stenogramm sport-type-fussball">
<header class="steno-header"><h1 class="steno-header-match">Home : Away</h1>
<h2 class="steno-header-time">6. Spieltag, 16.10.2026 20:30 Uhr</h2>
<h4 class="steno-header-league">Fußball, Männer, Bundesliga, 2026-2027</h4></header>
<div class="steno-head"><div class="steno-match-state">Ende</div>
<div class="steno-meta-info"><span class="date">16.10.2026</span><span class="time">20:30 Uhr</span></div>
<div class="steno-match"><div class="steno-teams">
<div class="steno-team"><div class="steno-team-head"><div class="steno-team-hl delta"><a href="https://www.ndr.de/sport/ergebnisse/fussballmaenner-486~_gameplan-mannschaftfussball264.html">Home</a></div></div></div>
<div class="steno-team"><div class="steno-team-head"><div class="steno-team-hl delta"><a href="https://www.ndr.de/sport/ergebnisse/fussballmaenner-486~_gameplan-mannschaftfussball110.html">Away</a></div></div></div>
</div><div class="steno-results"><span class="finalresult">1:0</span><span class="interimresult">(0:0)</span></div></div></div>
<div class="liveticker"><ul class="liveticker-list">{tick() if ticks is None else ticks}</ul></div>
</article></body></html>'''.encode()


class NDRCompletionObservationTests(unittest.TestCase):
    def reject(self, body, item=UNSET):
        with self.assertRaises(ValueError):
            parse_detail(body, expected() if item is UNSET else item)

    def test_explicit_same_event_completion_is_only_an_observed_display(self):
        item = expected()
        before = copy.deepcopy(item)
        got = parse_detail(detail(), item)
        self.assertEqual(item, before)
        self.assertEqual(got['schema'], 'football-king-ndr-completion-display-candidate-v1')
        self.assertEqual(got['provider_fixture_id'], '5884')
        self.assertEqual(got['fixture_url'], URL)
        self.assertEqual((got['home_provider_team_id'], got['away_provider_team_id']), ('264', '110'))
        self.assertEqual(got['date_local'], '2026-10-16')
        self.assertEqual(got['display_score'], {'home': 1, 'away': 0})
        self.assertEqual(got['interim_display_score'], {'home': 0, 'away': 0})
        self.assertEqual(got['completion_display'], 'Ende')
        self.assertEqual(got['end_event_clock'], {'base_minute': 90, 'stoppage_minute': 5})
        self.assertTrue(got['completion_display_observed'])
        self.assertTrue(got['candidate_only'])
        for key in ['completion_authenticated', 'period_authenticated', 'independently_verified', 'eligible_for_model_scoring']:
            self.assertIs(got[key], False)
        self.assertEqual(got['status'], 'HOLD')
        self.assertEqual(got['production_recommendations'], 'DISABLED')
        for key in ['score_ft', 'ft', 'y', 'result_verified', 'kickoff_utc', 'published_utc']:
            self.assertNotIn(key, got)

    def test_clock_is_bounded_display_only_and_zero_stoppage_supported(self):
        for clock, value in [('90. Min.', 0), ('90.<span>+0</span> Min.', 0), ('90.<span>+30</span> Min.', 30)]:
            with self.subTest(clock=clock):
                self.assertEqual(parse_detail(detail(tick(clock=clock)), expected())['end_event_clock']['stoppage_minute'], value)
        for clock in ['45.<span>+5</span> Min.', '89. Min.', '91. Min.', '105. Min.', '120. Min.', '90.<span>+31</span> Min.', '90.<span>-1</span> Min.', '90.5 Min.', '90.<b>+5</b> Min.', '90.<span>+5</span><span>+1</span> Min.']:
            with self.subTest(clock=clock):
                self.reject(detail(tick(clock=clock)))

    def test_half_time_event_cannot_replace_end_event(self):
        half = tick(clock='45.<span>+2</span> Min.', label='Ende 1. Halbzeit', icon=END_ICON.replace('end.svg', 'halftime.svg'), alt='Halbzeit')
        self.reject(detail(half))
        self.assertTrue(parse_detail(detail(tick() + half), expected())['completion_display_observed'])

    def test_live_and_half_time_states_are_rejected_even_with_end_event(self):
        for state in ['Live', 'Halbzeit', '90. Min.', 'Ende Live', 'Ende n.V.', 'Ende i.E.', 'beendet', 'Ende Verlängerung', 'Ende Elfmeterschießen']:
            with self.subTest(state=state):
                self.reject(detail().replace(b'>Ende<', f'>{state}<'.encode()))

    def test_identity_urls_must_be_unique_exact_and_in_head(self):
        for body in [detail().replace(URL.encode(), URL.replace('5884', '5885').encode(), 1),
                     detail().replace(b'5884.html', b'5884.html?x=1', 1),
                     detail().replace(b'rel="canonical"', b'rel="canonical" rel="alternate"'),
                     detail().replace(b'</head>', f'<meta property="og:url" content="{URL}"></head>'.encode()),
                     detail().replace(b'</head>', f'<link rel="canonical" href="{URL}"></head>'.encode()),
                     detail().replace(b'<head>', b'<body>').replace(b'</head>', b'</body>'),
                     detail().replace(b'<link rel="canonical"', b'<link rel="alternate"')]:
            with self.subTest(body=body):
                self.reject(body)

    def test_exact_season_date_and_header_date_agree_with_row(self):
        for old, new in [(b'2026-2027', b'2025-2026'), (b'16.10.2026</span>', b'17.10.2026</span>'),
                         (b'16.10.2026 20:30 Uhr', b'15.10.2026 20:30 Uhr'),
                         (b'16.10.2026 20:30 Uhr', b'31.02.2026 20:30 Uhr'),
                         (b'16.10.2026 20:30 Uhr', b'16.10.2026 26:80 Uhr')]:
            with self.subTest(new=new):
                self.reject(detail().replace(old, new))
        self.reject(detail().replace(b'</header>', '<h4 class="steno-header-league">Fußball, Männer, Bundesliga, 2026-2027</h4></header>'.encode()))

    def test_team_ids_order_urls_and_scopes_are_strict(self):
        for body in [detail().replace(b'mannschaftfussball264', b'mannschaftfussball999'),
                     detail().replace(b'mannschaftfussball264', b'mannschaftfussballTMP').replace(b'mannschaftfussball110', b'mannschaftfussball264').replace(b'mannschaftfussballTMP', b'mannschaftfussball110'),
                     detail().replace(b'ndr.de/sport/ergebnisse/fussballmaenner', b'evil.example/sport/ergebnisse/fussballmaenner', 1),
                     detail().replace(b'steno-team-hl delta', b'unrelated', 1),
                     detail().replace(b'</a>', b'</a><a href="https://www.ndr.de/sport/ergebnisse/fussballmaenner-486~_gameplan-mannschaftfussball264.html">Extra</a>', 1)]:
            with self.subTest(body=body):
                self.reject(body)

    def test_lineup_reuses_team_headings_but_cannot_supply_match_identity(self):
        lineup = b'<div id="tab-3"><div class="steno-team-head"><div class="steno-team-hl">Home</div></div><div class="steno-team-head"><div class="steno-team-hl">Away</div></div></div>'
        body = detail().replace(b'</article>', lineup + b'</article>')
        self.assertTrue(parse_detail(body, expected())['completion_display_observed'])
        self.reject(body.replace(b'class="steno-team-hl delta"', b'class="unrelated"', 1))

    def test_detail_header_and_end_event_scores_must_match_expected_row(self):
        for body in [detail().replace(b'finalresult">1:0', b'finalresult">2:0'),
                     detail(tick(score='2:0')),
                     detail().replace(b'interimresult">(0:0)', b'interimresult">(1:0)'),
                     detail().replace(b'finalresult">1:0', b'finalresult"><b>1:0</b>'),
                     detail().replace(b'finalresult">1:0', b'finalresult">31:0'),
                     detail().replace(b'<span class="finalresult">1:0</span>', b'<span class="finalresult">1:0</span><span class="finalresult">2:0</span>')]:
            with self.subTest(body=body):
                self.reject(body)

    def test_end_event_requires_its_own_unique_clock_icon_label_and_score(self):
        for one in [tick().replace('liveticker-time theta', 'unrelated'),
                    tick().replace('liveticker-headline-score', 'unrelated'),
                    tick(label='Ende'), tick(label='Spielende Live'), tick(alt='Ende'),
                    tick(icon=END_ICON + '?x=1'), tick().replace('incident-icon', 'unrelated'),
                    tick().replace('<b>Spielende</b>', '<span>Spielende</span>')]:
            with self.subTest(one=one):
                self.reject(detail(one))
        for one in [tick() + tick(), tick() + tick(score='2:0'), tick() + tick(clock='120. Min.'),
                    tick().replace('</li>', '<div class="liveticker-time">90. Min.</div></li>')]:
            with self.subTest(one=one):
                self.reject(detail(one))

    def test_split_event_scopes_never_complete_each_other(self):
        first = tick().replace('<b>Spielende</b>', '<b>Other</b>')
        second = tick().replace(f'<img class="incident-icon" src="{END_ICON}" alt="Spielende">', '')
        self.reject(detail(first + second))
        self.reject(detail().replace(b'<li class="liveticker-item">', b'<div class="liveticker-item">').replace(b'</li>', b'</div>'))

    def test_extra_time_penalty_states_and_later_event_clocks_rejected(self):
        for extra in [tick(clock='105. Min.', label='Anpfiff Verlängerung', icon='/other.svg', alt='Anpfiff'),
                      tick(clock='120. Min.', label='Ende Verlängerung', icon='/other.svg', alt='Ende'),
                      tick(label='Elfmeterschießen', icon='/other.svg', alt='Elfmeterschießen')]:
            with self.subTest(extra=extra):
                self.reject(detail(tick() + extra))
        for state in ['live', 'halftime', 'half-time', 'extra-time', 'penalties']:
            with self.subTest(state=state):
                self.reject(detail().replace(b'class="steno-match-state"', f'class="steno-match-state {state}"'.encode()))

    def test_inert_article_wrappers_and_in_article_active_content_fail_closed(self):
        for tag in ['script', 'style', 'template', 'noscript', 'svg', 'math', 'iframe', 'object', 'xmp', 'plaintext', 'title', 'textarea', 'select', 'option', 'optgroup', 'datalist']:
            with self.subTest(tag=tag):
                body = detail()
                start, end = body.index(b'<article'), body.index(b'</article>') + len(b'</article>')
                self.reject(body[:start] + f'<{tag}>'.encode() + body[start:end] + f'</{tag}>'.encode() + body[end:])
                self.reject(body.replace(b'>Ende<', f'><{tag}>Ende</{tag}><'.encode()))

    def test_visibility_and_hidden_marker_scopes_rejected(self):
        for attrs in [b' hidden', b' hidden="hidden"', b' aria-hidden="true"', b' inert', b' style="display:none"', b' style="visibility:hidden"']:
            with self.subTest(attrs=attrs):
                self.reject(detail().replace(b'<article class=', b'<article' + attrs + b' class='))
                self.reject(detail().replace(b'<body>', b'<body><div' + attrs + b'>').replace(b'</body>', b'</div></body>'))

    def test_nested_ambiguous_duplicate_and_malformed_scopes_fail_closed(self):
        for body in [detail() + detail(), detail().replace(b'</article>', b''),
                     detail().replace(b'</article>', b'<article class="page-sport-stenogramm sport-type-fussball"></article></article>'),
                     detail().replace(b'class="finalresult"', b'class="finalresult" class="other"'),
                     detail().replace(b'>Ende<', b'/>Ende<'),
                     detail().replace(b'</span><span class="interimresult">', b'</div><span class="interimresult">'),
                     detail().replace(b'<span class="finalresult">', b'<span class="finalresult"/>')]:
            with self.subTest(body=body):
                self.reject(body)

    def test_expected_row_identity_exact_types_and_safe_flags(self):
        attacks = [('provider', 'OTHER'), ('provider_fixture_id', 5884), ('provider_fixture_id', '05884'),
                   ('fixture_url', URL + '?x=1'), ('season', '2025-2026'), ('date_local', '2026-10-17'),
                   ('home_provider_team_id', 264), ('home_provider_team_id', '0264'),
                   ('away_provider_team_id', '264'), ('home_provider_team_url', 'https://evil.example/264'),
                   ('display_score', {'home': True, 'away': 0}), ('display_score', {'home': 1.0, 'away': 0}),
                   ('display_score', {'home': 1, 'away': 0, 'extra': 0}), ('display_score', {'home': 31, 'away': 0}),
                   ('interim_display_score', {'home': 1, 'away': 0}), ('candidate_only', False),
                   ('completion_status_unverified', False), ('result_period_unverified', False),
                   ('independently_verified', True), ('eligible_for_model_scoring', True),
                   ('date_year_inferred_from_season', False), ('date_year_context', 'anything'),
                   ('display_field', 'score_ft'), ('status', 'READY'), ('production_recommendations', 'ENABLED'),
                   ('completion_authenticated', True), ('period_authenticated', True), ('result_verified', True), ('y', 1), ('score_ft', '1:0')]
        for key, value in attacks:
            with self.subTest(key=key, value=value):
                item = expected()
                item[key] = value
                self.reject(detail(), item)
        for item in [None, [], True, {}, dict(expected(), display_score=None)]:
            self.reject(detail(), item)

    def test_input_bytes_encoding_size_and_tree_bounds(self):
        for body in [None, '', bytearray(detail()), b'', b'\xff', b'x' * (MAX_BYTES + 1),
                     detail().replace(b'>Ende<', b'>' + b'<div>' * 65 + b'Ende' + b'</div>' * 65 + b'<'),
                     detail().replace(b'>Ende<', b'>' + b'<span></span>' * 30_001 + b'Ende<')]:
            with self.subTest(body_type=type(body).__name__):
                self.reject(body)


if __name__ == '__main__':
    unittest.main()
