"""Observe an explicit NDR completion display without authenticating a result.

This offline parser accepts only one bounded, structurally unambiguous football
detail article agreeing with an existing NDR row observation. ``Ende`` and the
90-minute ``Spielende`` event are source displays, never proof of the result's
period, source independence, UTC kickoff, or eligibility for model scoring.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser


MAX_BYTES = 3_000_000
MAX_NODES = 30_000
MAX_DEPTH = 64
LEAGUE = 'Fußball, Männer, Bundesliga, 2026-2027'
END_ICON = '/resources/assets/resources/images/svg/icons/sport-ticker-end.svg'
ID = re.compile(r'[1-9][0-9]{0,9}\Z')
TEAM_PREFIX = 'https://www.ndr.de/sport/ergebnisse/fussballmaenner-486~_gameplan-mannschaftfussball'
FIXTURE_PREFIX = 'https://www.ndr.de/sport/ergebnisse/spielstatistik-'
VOID_TAGS = frozenset(('area', 'base', 'br', 'col', 'embed', 'hr', 'img',
                       'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'))
INERT_TAGS = frozenset(('script', 'style', 'template', 'noscript', 'svg',
                        'math', 'iframe', 'object', 'xmp', 'plaintext', 'title',
                        'textarea', 'select', 'option', 'optgroup', 'datalist'))
HIDDEN_CLASSES = frozenset(('hidden', 'hide', 'is-hidden', 'd-none', 'sr-only',
                            'visually-hidden'))
NON_REGULATION = re.compile(r'verlängerung|elfmeterschie(?:ß|ss)en|extra[ -]?time|penalt(?:y|ies)|\bn\s*\.\s*v\s*\.|\bi\s*\.\s*e\s*\.', re.I)


@dataclass(eq=False)
class _Node:
    tag: str
    attrs: dict
    parent: object = None
    children: list = field(default_factory=list)

    def classes(self):
        return set(self.attrs.get('class', '').split())

    def descendants(self, tag=None, css=None):
        pending, found = list(reversed(self.children)), []
        while pending:
            node = pending.pop()
            if isinstance(node, _Node):
                if (tag is None or node.tag == tag) and (css is None or css in node.classes()):
                    found.append(node)
                pending.extend(reversed(node.children))
        return found

    def text(self):
        pending, pieces = list(reversed(self.children)), []
        while pending:
            node = pending.pop()
            if isinstance(node, _Node):
                pending.extend(reversed(node.children))
            else:
                pieces.append(node)
        return ''.join(pieces)


class _DetailParser(HTMLParser):
    """A strict bounded tree; no browser repair of ambiguous source markup."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node('_document', {})
        self.stack = [self.root]
        self.nodes = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if len(values) != len(attrs):
            raise ValueError('DUPLICATE_NDR_DETAIL_ATTRIBUTE')
        # Boolean HTML attributes are valid but still subject to visibility checks.
        values = {key: '' if value is None else value for key, value in values.items()}
        self.nodes += 1
        if self.nodes > MAX_NODES or len(self.stack) > MAX_DEPTH:
            raise ValueError('NDR_DETAIL_HTML_LIMIT_EXCEEDED')
        node = _Node(tag, values, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID_TAGS:
            # Real site chrome contains self-closing SVG paths. Foreign content
            # cannot contain the accepted article, and remains inert evidence.
            foreign = any(node.tag in {'svg', 'math'} for node in self.stack)
            if not foreign or tag in INERT_TAGS or tag == 'article':
                raise ValueError('NON_VOID_SELF_CLOSING_NDR_DETAIL_HTML')
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS or len(self.stack) <= 1 or self.stack[-1].tag != tag:
            raise ValueError('MALFORMED_NDR_DETAIL_HTML')
        self.stack.pop()

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _single(nodes, reason):
    if len(nodes) != 1:
        raise ValueError(reason)
    return nodes[0]


def _visible(node, decorative=False):
    current = node
    while current is not None:
        attrs = current.attrs
        if current.tag in INERT_TAGS or 'hidden' in attrs or 'inert' in attrs or attrs.get('style', '').strip() or HIDDEN_CLASSES & current.classes():
            raise ValueError('INERT_OR_HIDDEN_NDR_DETAIL_EVIDENCE')
        if attrs.get('aria-hidden', '').strip().lower() == 'true' and not (decorative and current is node):
            raise ValueError('INERT_OR_HIDDEN_NDR_DETAIL_EVIDENCE')
        current = current.parent


def _plain(node):
    _visible(node)
    if any(isinstance(child, _Node) for child in node.children):
        raise ValueError('NON_TEXT_NDR_DETAIL_DISPLAY')
    return node.text().strip()


def _one_in(article, scope, tag, css):
    node = _single(scope.descendants(tag, css), 'MISSING_OR_AMBIGUOUS_NDR_DETAIL_' + css.upper())
    if article.descendants(css=css) != [node]:
        raise ValueError('CROSS_SCOPE_NDR_DETAIL_' + css.upper())
    _visible(node)
    return node


def _score_value(value):
    if not isinstance(value, dict) or set(value) != {'home', 'away'} or any(type(value[key]) is not int or not 0 <= value[key] <= 30 for key in ('home', 'away')):
        raise ValueError('INVALID_EXPECTED_NDR_DISPLAY_SCORE')
    return {'home': value['home'], 'away': value['away']}


def _display_score(node, interim=False):
    pattern = r'\(([0-9]{1,2}):([0-9]{1,2})\)' if interim else r'([0-9]{1,2}):([0-9]{1,2})'
    match = re.fullmatch(pattern, _plain(node))
    if not match:
        raise ValueError('INVALID_NDR_DETAIL_SCORE_DISPLAY')
    return _score_value(dict(zip(('home', 'away'), map(int, match.groups()))))


def _expected_row(item):
    if not isinstance(item, dict):
        raise ValueError('INVALID_EXPECTED_NDR_ROW')
    required = {'provider': 'NDR', 'season': '2026-2027', 'display_field': 'finalresult',
                'date_year_context': 'EXACT_SEASON_TABLE_JULY_JUNE_LOCAL_DATE_ONLY'}
    if any(type(item.get(key)) is not str or item[key] != value for key, value in required.items()):
        raise ValueError('INVALID_EXPECTED_NDR_ROW_CONTEXT')
    for key in ('candidate_only', 'completion_status_unverified', 'result_period_unverified', 'date_year_inferred_from_season'):
        if item.get(key) is not True:
            raise ValueError('UNSAFE_EXPECTED_NDR_ROW_FLAGS')
    for key in ('independently_verified', 'eligible_for_model_scoring'):
        if item.get(key) is not False:
            raise ValueError('UNSAFE_EXPECTED_NDR_ROW_FLAGS')
    for key in ('completion_authenticated', 'period_authenticated'):
        if key in item and item[key] is not False:
            raise ValueError('UNSAFE_EXPECTED_NDR_ROW_FLAGS')
    if ('status' in item and item['status'] != 'HOLD') or ('production_recommendations' in item and item['production_recommendations'] != 'DISABLED') or any(key in item for key in ('score_ft', 'ft', 'y', 'result_verified')):
        raise ValueError('UNSAFE_EXPECTED_NDR_ROW_FLAGS')
    for key in ('provider_fixture_id', 'home_provider_team_id', 'away_provider_team_id'):
        if type(item.get(key)) is not str or not ID.fullmatch(item[key]):
            raise ValueError('INVALID_EXPECTED_NDR_IDENTITY')
    if item['home_provider_team_id'] == item['away_provider_team_id']:
        raise ValueError('INVALID_EXPECTED_NDR_IDENTITY')
    urls = {'fixture_url': FIXTURE_PREFIX + item['provider_fixture_id'] + '.html',
            'home_provider_team_url': TEAM_PREFIX + item['home_provider_team_id'] + '.html',
            'away_provider_team_url': TEAM_PREFIX + item['away_provider_team_id'] + '.html'}
    if any(type(item.get(key)) is not str or item[key] != value for key, value in urls.items()):
        raise ValueError('INVALID_EXPECTED_NDR_IDENTITY_URL')
    local = item.get('date_local')
    if type(local) is not str or not re.fullmatch(r'202[67]-[0-9]{2}-[0-9]{2}', local):
        raise ValueError('INVALID_EXPECTED_NDR_DATE')
    try:
        calendar = date.fromisoformat(local)
    except ValueError as exc:
        raise ValueError('INVALID_EXPECTED_NDR_DATE') from exc
    if not date(2026, 7, 1) <= calendar <= date(2027, 6, 30):
        raise ValueError('INVALID_EXPECTED_NDR_DATE')
    return calendar, _score_value(item.get('display_score')), _score_value(item.get('interim_display_score'))


def _clock(node):
    _visible(node)
    spans = [child for child in node.children if isinstance(child, _Node)]
    if len(spans) > 1 or any(child.tag != 'span' for child in spans):
        raise ValueError('INVALID_NDR_EVENT_CLOCK')
    if spans and not re.fullmatch(r'\+(?:0|[1-9][0-9]?)', _plain(spans[0])):
        raise ValueError('INVALID_NDR_EVENT_CLOCK')
    match = re.fullmatch(r'(0|[1-9][0-9]{0,2})\.(?:\+(0|[1-9][0-9]?))?\s+Min\.', node.text().strip())
    if not match or bool(spans) != (match.group(2) is not None):
        raise ValueError('INVALID_NDR_EVENT_CLOCK')
    base, stoppage = int(match.group(1)), int(match.group(2) or 0)
    if base > 90 or stoppage > 30:
        raise ValueError('NON_REGULATION_OR_INVALID_NDR_EVENT_CLOCK')
    return base, stoppage


def _completion_event(article):
    ticker = _one_in(article, article, 'div', 'liveticker')
    listing = _one_in(article, ticker, 'ul', 'liveticker-list')
    events = listing.descendants('li', 'liveticker-item')
    if not events or article.descendants(css='liveticker-item') != events or any(event.parent is not listing for event in events):
        raise ValueError('AMBIGUOUS_NDR_EVENT_SCOPE')
    event_set = set(events)
    markers = []
    for node in article.descendants():
        is_icon = node.tag == 'img' and (node.attrs.get('src') == END_ICON or node.attrs.get('alt') == 'Spielende')
        is_label = node.tag == 'b' and re.search(r'\bSpielende\b', node.text())
        if is_icon or is_label:
            parent = node.parent
            while parent is not None and parent not in event_set:
                parent = parent.parent
            if parent is None:
                raise ValueError('CROSS_SCOPE_NDR_END_EVENT')
            markers.append((node, parent))
        # Only structured event labels/icons identify extra-time/penalty phases;
        # ordinary match commentary may mention other games or previous halves.
        structural = node.text() if node.tag == 'b' else ' '.join((node.attrs.get('alt', ''), node.attrs.get('src', ''))) if node.tag == 'img' else ''
        if NON_REGULATION.search(structural) or {'live', 'halftime', 'half-time', 'extra-time', 'penalties'} & node.classes():
            raise ValueError('NON_REGULATION_NDR_EVENT_MARKER')
    end_events = {event for _, event in markers}
    if len(end_events) != 1:
        raise ValueError('MISSING_OR_AMBIGUOUS_NDR_END_EVENT')
    event = end_events.pop()
    _visible(event)
    clock = _clock(_single(event.descendants('div', 'liveticker-time'), 'MISSING_OR_AMBIGUOUS_NDR_END_CLOCK'))
    if clock[0] != 90:
        raise ValueError('NDR_END_CLOCK_IS_NOT_90_MINUTES')
    headline = _single(event.descendants('div', 'liveticker-headline'), 'AMBIGUOUS_NDR_END_HEADLINE')
    score_node = _single(headline.descendants('span', 'liveticker-headline-score'), 'MISSING_OR_AMBIGUOUS_NDR_END_SCORE')
    if event.descendants(css='liveticker-headline-score') != [score_node]:
        raise ValueError('CROSS_SCOPE_NDR_END_SCORE')
    score = _display_score(score_node)
    subhead = _single(event.descendants('div', 'liveticker-subhead'), 'MISSING_OR_AMBIGUOUS_NDR_END_ICON')
    icon = _single(subhead.descendants('img', 'incident-icon'), 'MISSING_OR_AMBIGUOUS_NDR_END_ICON')
    _visible(icon, decorative=True)
    if event.descendants(css='incident-icon') != [icon] or icon.attrs.get('src') != END_ICON or icon.attrs.get('alt') != 'Spielende':
        raise ValueError('INVALID_NDR_END_ICON')
    text = _single(event.descendants('div', 'liveticker-text'), 'MISSING_OR_AMBIGUOUS_NDR_END_LABEL')
    label = _single(text.descendants('b'), 'MISSING_OR_AMBIGUOUS_NDR_END_LABEL')
    if _plain(label) != 'Spielende' or text.text().strip() != 'Spielende' or [child for child in text.children if isinstance(child, _Node)] != [label]:
        raise ValueError('INVALID_NDR_END_LABEL')
    if {node for node, _ in markers} != {icon, label}:
        raise ValueError('DUPLICATE_OR_CONFLICTING_NDR_END_MARKER')
    all_clocks = article.descendants(css='liveticker-time')
    nested_clocks = [node for item in events for node in item.descendants('div', 'liveticker-time')]
    if set(all_clocks) != set(nested_clocks):
        raise ValueError('CROSS_SCOPE_NDR_EVENT_CLOCK')
    for item in events:
        times = item.descendants('div', 'liveticker-time')
        if len(times) > 1 or (times and _clock(times[0]) > clock):
            raise ValueError('CONTRADICTORY_NDR_EVENT_CLOCK')
    return score, clock


def parse_detail(raw: bytes, expected_row: dict) -> dict:
    """Return one unauthenticated candidate, raising ValueError on any rejection.

    ``expected_row`` must be the safe observation produced by the existing NDR
    results-row parser. Its fixed IDs, exact URLs, local date and score displays
    are crosschecked; names, event clocks and local dates never supply UTC time.
    """
    calendar, expected_score, expected_interim = _expected_row(expected_row)
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES:
        raise ValueError('INVALID_OR_OVERSIZED_NDR_DETAIL_HTML')
    try:
        source = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise ValueError('INVALID_NDR_DETAIL_ENCODING') from exc
    parser = _DetailParser()
    try:
        parser.feed(source)
        parser.close()
    except (AssertionError, RecursionError) as exc:
        raise ValueError('MALFORMED_NDR_DETAIL_HTML') from exc
    if len(parser.stack) != 1:
        raise ValueError('UNCLOSED_NDR_DETAIL_HTML')
    root = parser.root
    html = _single(root.descendants('html'), 'MISSING_OR_AMBIGUOUS_NDR_HTML')
    head = _single(root.descendants('head'), 'MISSING_OR_AMBIGUOUS_NDR_HEAD')
    body = _single(root.descendants('body'), 'MISSING_OR_AMBIGUOUS_NDR_BODY')
    if html.parent is not root or head.parent is not html or body.parent is not html:
        raise ValueError('MALFORMED_NDR_DOCUMENT_SCOPE')
    canonical = _single([node for node in root.descendants('link') if 'canonical' in node.attrs.get('rel', '').split()], 'MISSING_OR_AMBIGUOUS_NDR_CANONICAL')
    og = _single([node for node in root.descendants('meta') if node.attrs.get('property') == 'og:url'], 'MISSING_OR_AMBIGUOUS_NDR_OG_URL')
    if canonical.parent is not head or og.parent is not head or canonical.attrs.get('rel') != 'canonical' or canonical.attrs.get('href') != expected_row['fixture_url'] or og.attrs.get('content') != expected_row['fixture_url'] or root.descendants('base'):
        raise ValueError('NDR_FIXTURE_URL_MISMATCH_OR_SCOPE')
    article = _single(root.descendants(css='page-sport-stenogramm'), 'MISSING_OR_AMBIGUOUS_NDR_ARTICLE')
    if article.parent is not body or article.tag != 'article' or {value for value in article.classes() if value.startswith('sport-type-')} != {'sport-type-fussball'}:
        raise ValueError('UNSUPPORTED_NDR_ARTICLE_CONTEXT')
    _visible(article)
    if any(node.tag in INERT_TAGS for node in article.descendants()):
        raise ValueError('ACTIVE_OR_INERT_CONTENT_IN_NDR_ARTICLE')
    header = _one_in(article, article, 'header', 'steno-header')
    if header.parent is not article:
        raise ValueError('MALFORMED_NDR_HEADER_SCOPE')
    league = _one_in(article, header, 'h4', 'steno-header-league')
    when = _one_in(article, header, 'h2', 'steno-header-time')
    if league.parent is not header or when.parent is not header or _plain(league) != LEAGUE:
        raise ValueError('NDR_LEAGUE_CONTEXT_MISMATCH')
    header_date = re.fullmatch(r'[1-9][0-9]{0,2}\. Spieltag, ([0-9]{2}\.[0-9]{2}\.[0-9]{4}) ((?:[01][0-9]|2[0-3]):[0-5][0-9]) Uhr', _plain(when))
    date_display = calendar.strftime('%d.%m.%Y')
    if not header_date or header_date.group(1) != date_display:
        raise ValueError('NDR_HEADER_DATE_MISMATCH')
    summary = _one_in(article, article, 'div', 'steno-head')
    state = _one_in(article, summary, 'div', 'steno-match-state')
    meta = _one_in(article, summary, 'div', 'steno-meta-info')
    local = _single(meta.descendants('span', 'date'), 'MISSING_OR_AMBIGUOUS_NDR_DATE')
    local_time = _single(meta.descendants('span', 'time'), 'MISSING_OR_AMBIGUOUS_NDR_LOCAL_TIME')
    if _plain(state) != 'Ende' or _plain(local) != date_display or _plain(local_time) != header_date.group(2) + ' Uhr':
        raise ValueError('NDR_COMPLETION_STATE_OR_DATE_MISMATCH')
    match = _one_in(article, summary, 'div', 'steno-match')
    if state.parent is not meta.parent or meta.parent is not match.parent:
        raise ValueError('CROSS_SCOPE_NDR_MATCH_SUMMARY')
    teams = _one_in(article, match, 'div', 'steno-teams')
    headings = teams.descendants('div', 'steno-team-hl')
    # The line-up tab repeats steno-team-hl headings; only steno-teams supplies
    # this ordered match identity. Other tabs cannot fill a missing heading.
    if len(headings) != 2 or len(teams.descendants('a')) != 2:
        raise ValueError('AMBIGUOUS_NDR_TEAM_IDENTITY')
    wrappers = [child for child in teams.children if isinstance(child, _Node)]
    if len(wrappers) != 2 or any(child.tag != 'div' or 'steno-team' not in child.classes() for child in wrappers):
        raise ValueError('AMBIGUOUS_NDR_TEAM_IDENTITY')
    for heading, wrapper, key in zip(headings, wrappers, ('home_provider_team_url', 'away_provider_team_url')):
        anchor = _single(heading.descendants('a'), 'AMBIGUOUS_NDR_TEAM_IDENTITY')
        _visible(anchor)
        if wrapper.descendants('div', 'steno-team-hl') != [heading] or heading.parent is None or 'steno-team-head' not in heading.parent.classes() or anchor.parent is not heading or anchor.attrs.get('href') != expected_row[key] or not anchor.text().strip():
            raise ValueError('NDR_ORDERED_TEAM_IDENTITY_MISMATCH')
    results = _one_in(article, match, 'div', 'steno-results')
    score = _display_score(_one_in(article, results, 'span', 'finalresult'))
    interim = _display_score(_one_in(article, results, 'span', 'interimresult'), interim=True)
    end_score, clock = _completion_event(article)
    if score != expected_score or score != end_score or interim != expected_interim or any(interim[side] > score[side] for side in ('home', 'away')):
        raise ValueError('CONFLICTING_NDR_SCORE_DISPLAYS')
    identity_keys = ('provider', 'provider_fixture_id', 'fixture_url', 'home_provider_team_id',
                     'away_provider_team_id', 'home_provider_team_url', 'away_provider_team_url', 'season', 'date_local')
    return {
        'schema': 'football-king-ndr-completion-display-candidate-v1',
        **{key: expected_row[key] for key in identity_keys},
        'display_score': score, 'interim_display_score': interim,
        'completion_display': 'Ende', 'completion_display_observed': True,
        'end_event_display': 'Spielende',
        'end_event_clock': {'base_minute': clock[0], 'stoppage_minute': clock[1]},
        'completion_authenticated': False, 'period_authenticated': False,
        'completion_status_unverified': True, 'result_period_unverified': True,
        'independently_verified': False, 'eligible_for_model_scoring': False,
        'candidate_only': True, 'status': 'HOLD', 'production_recommendations': 'DISABLED',
    }
