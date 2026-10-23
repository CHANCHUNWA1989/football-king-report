"""Parse NDR row-local score displays, never authenticated full-time outcomes.

The CSS name ``finalresult`` identifies a display field; it does not establish
that a match has finished or that its score refers to regulation time. Source
bytes, capture metadata, provider IDs and display observations stay quarantined
from every model-scoring and production-promotion interface.
"""
import argparse
import hashlib
import json
import re
import stat
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SOURCE_URL = ('https://www.ndr.de/sport/ergebnisse/'
              'Alle-Ergebnisse-Fussball-Bundesliga-2026-2027%2Cfussballmaenner-486.html')
TABLE_SUMMARY = 'Fußball, Männer, Bundesliga, 2026-2027'
MAX_BYTES = 3_000_000
MAX_MANIFEST_BYTES = 65_536
MAX_NODES = 30_000
MAX_ROWS = 400
VOID_TAGS = frozenset(('area', 'base', 'br', 'col', 'embed', 'hr', 'img',
                       'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'))
INERT_TAGS = frozenset(('script', 'style', 'template', 'noscript', 'svg',
                        'math', 'iframe', 'object', 'xmp', 'plaintext'))
TEAM_PATH = re.compile(r'/sport/ergebnisse/fussballmaenner-486~_gameplan-mannschaftfussball([1-9][0-9]{0,9})\.html\Z')
FIXTURE_PATH = re.compile(r'https://www\.ndr\.de/sport/ergebnisse/spielstatistik-([1-9][0-9]{0,9})\.html\Z')
LIVE_MARKER = re.compile(r'\b(?:live|halbzeit|spielminute|minute|verlängerung|elfmeterschießen)\b|\bn\s*\.\s*v\s*\.|\bi\s*\.\s*e\s*\.|\d{1,3}\s*[\u2032\u2019\']', re.I)


@dataclass
class _Node:
    tag: str
    attrs: dict
    children: list = field(default_factory=list)

    def classes(self):
        return set(self.attrs.get('class', '').split())

    def descendants(self, tag=None, css=None):
        result = []
        for child in self.children:
            if isinstance(child, _Node):
                if (tag is None or child.tag == tag) and (css is None or css in child.classes()):
                    result.append(child)
                result.extend(child.descendants(tag, css))
        return result

    def text(self):
        return ''.join(child.text() if isinstance(child, _Node) else child for child in self.children)


class _ResultsParser(HTMLParser):
    """Build a bounded strict subtree of the single designated results table."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.stack = []
        self.nodes = 0
        self.outside_inert = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        is_results = tag == 'table' and {'datatable', 'results'} <= set((values.get('class') or '').split())
        if not self.stack:
            if is_results and self.outside_inert:
                raise ValueError('INERT_RESULTS_TABLE')
            if tag in INERT_TAGS:
                self.outside_inert.append(tag)
            if not is_results:
                return
        if len(values) != len(attrs) or any(value is None for value in values.values()):
            raise ValueError('MALFORMED_RESULTS_ATTRIBUTES')
        if is_results and not self.stack:
            if self.tables or values.get('summary') != TABLE_SUMMARY:
                raise ValueError('AMBIGUOUS_OR_UNSUPPORTED_RESULTS_TABLE')
        elif tag == 'table':
            raise ValueError('NESTED_RESULTS_TABLE')
        if tag == 'tr':
            if any(node.tag == 'tr' for node in self.stack):
                raise ValueError('NESTED_RESULT_ROW')
            if not self.stack or self.stack[-1].tag not in {'table', 'thead', 'tbody', 'tfoot'}:
                raise ValueError('MALFORMED_RESULT_ROW_PARENT')
        if tag == 'td' and (not self.stack or self.stack[-1].tag != 'tr'):
            raise ValueError('MALFORMED_RESULT_CELL')
        self.nodes += 1
        if self.nodes > MAX_NODES or len(self.stack) >= 64:
            raise ValueError('RESULTS_HTML_LIMIT_EXCEEDED')
        node = _Node(tag, values)
        if self.stack:
            self.stack[-1].children.append(node)
        else:
            self.tables.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        # HTML does not close non-void elements merely because '/>' appears.
        # Refuse these ambiguous forms instead of giving inert contents visibility.
        if tag not in VOID_TAGS and (self.stack or tag in INERT_TAGS or tag == 'table'):
            raise ValueError('NON_VOID_SELF_CLOSING_HTML')
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            if self.outside_inert and tag == self.outside_inert[-1]:
                self.outside_inert.pop()
            return
        if tag in VOID_TAGS or self.stack[-1].tag != tag:
            raise ValueError('MALFORMED_RESULTS_HTML')
        self.stack.pop()

    def handle_data(self, data):
        if self.stack:
            self.stack[-1].children.append(data)


def _score(node, interim=False):
    if node.children and any(isinstance(child, _Node) for child in node.children):
        raise ValueError('NON_TEXT_SCORE_DISPLAY')
    pattern = r'\(([0-9]{1,2}):([0-9]{1,2})\)' if interim else r'([0-9]{1,2}):([0-9]{1,2})'
    match = re.fullmatch(pattern, node.text().strip())
    if not match:
        raise ValueError('INVALID_SCORE_DISPLAY')
    home, away = (int(value) for value in match.groups())
    if home > 30 or away > 30:
        raise ValueError('SCORE_DISPLAY_OUT_OF_RANGE')
    return {'home': home, 'away': away}


def _single(nodes, reason):
    if len(nodes) != 1:
        raise ValueError(reason)
    return nodes[0]


def _row_observation(row):
    # Identity/date/score must all originate from this row's designated cells.
    cells = [node for node in row.children if isinstance(node, _Node)]
    if len(cells) != 4 or any(cell.tag != 'td' for cell in cells):
        raise ValueError('INVALID_RESULT_ROW_CELLS')
    if [cell.attrs.get('headers') for cell in cells] != [f'results-col-{i}' for i in range(1, 5)]:
        raise ValueError('INVALID_RESULT_ROW_CELL_HEADERS')
    if any(row.descendants(tag) for tag in INERT_TAGS):
        raise ValueError('ACTIVE_CONTENT_IN_RESULT_ROW')
    # These tokens can explicitly contradict a completed regulation-time result.
    # Even when none exist, completion and result period remain unverified.
    # Audio-Live is an action offered even on old result rows, not a status.
    # Exclude only the observed, explicitly typed Sportschau audio action.
    audio_actions = [anchor for anchor in cells[3].descendants('a')
                     if anchor.attrs.get('href', '').startswith('https://www.sportschau.de/')
                     and len(anchor.descendants(css='icon-audio')) == 1]
    action_text = ' '.join(anchor.text() for anchor in cells[3].descendants('a')
                           if anchor not in audio_actions)
    marker_text = ' '.join([cells[0].text(), cells[1].text(), cells[2].text(), action_text])
    if LIVE_MARKER.search(marker_text) or any(
            {'live', 'liveticker', 'extra-time', 'penalties'} & node.classes()
            for node in [row, *row.descendants()]):
        raise ValueError('LIVE_OR_NON_REGULATION_MARKER')
    date_node = _single(cells[0].descendants(css='date'), 'DATE_MISSING_OR_AMBIGUOUS')
    if len(row.descendants(css='date')) != 1:
        raise ValueError('DATE_MISSING_OR_AMBIGUOUS')
    if any(isinstance(child, _Node) for child in date_node.children):
        raise ValueError('INVALID_DATE_DISPLAY')
    date_match = re.fullmatch(r'([0-9]{2})\.([0-9]{2})\.', date_node.text().strip())
    if not date_match:
        raise ValueError('INVALID_DATE_DISPLAY')
    day, month = (int(value) for value in date_match.groups())
    # Explicit July-June interpretation of the exact 2026-2027 season context.
    # This is a local calendar date, never an independently authenticated kickoff.
    try:
        local_date = date(2026 if month >= 7 else 2027, month, day)
    except ValueError as exc:
        raise ValueError('INVALID_DATE_DISPLAY') from exc
    wrappers = cells[1].descendants(css='teamwrapper')
    if len(wrappers) != 2 or len(row.descendants(css='teamwrapper')) != 2 or len(cells[1].descendants('a')) != 2:
        raise ValueError('TEAM_IDENTITY_MISSING_OR_AMBIGUOUS')
    team_ids, team_urls = [], []
    for wrapper in wrappers:
        anchor = _single(wrapper.descendants('a'), 'TEAM_IDENTITY_MISSING_OR_AMBIGUOUS')
        if len(anchor.descendants(css='teamname')) != 1:
            raise ValueError('TEAM_IDENTITY_MISSING_OR_AMBIGUOUS')
        href = anchor.attrs.get('href', '')
        path = href.removeprefix('https://www.ndr.de')
        match = TEAM_PATH.fullmatch(path)
        if not match:
            raise ValueError('TEAM_IDENTITY_MISSING_OR_AMBIGUOUS')
        team_ids.append(match.group(1))
        team_urls.append('https://www.ndr.de' + path)
    if team_ids[0] == team_ids[1]:
        raise ValueError('TEAM_IDENTITY_MISSING_OR_AMBIGUOUS')
    score = _score(_single(cells[2].descendants('span', 'finalresult'), 'SCORE_MISSING_OR_AMBIGUOUS'))
    # Reject a score-field class appearing outside its designated score cell.
    if len(row.descendants(css='finalresult')) != 1:
        raise ValueError('SCORE_MISSING_OR_AMBIGUOUS')
    interim_nodes = cells[2].descendants('span', 'interimresult')
    if len(interim_nodes) > 1 or len(row.descendants(css='interimresult')) != len(interim_nodes):
        raise ValueError('INTERIM_SCORE_AMBIGUOUS')
    interim = _score(interim_nodes[0], interim=True) if interim_nodes else None
    details = [anchor for anchor in cells[3].descendants('a') if anchor not in audio_actions]
    detail = _single(details, 'FIXTURE_IDENTITY_MISSING_OR_AMBIGUOUS')
    fixture_url = detail.attrs.get('href', '')
    fixture_match = FIXTURE_PATH.fullmatch(fixture_url)
    if not fixture_match:
        raise ValueError('FIXTURE_IDENTITY_MISSING_OR_AMBIGUOUS')
    return {
        'provider': 'NDR', 'provider_fixture_id': fixture_match.group(1),
        'fixture_url': fixture_url, 'home_provider_team_id': team_ids[0],
        'away_provider_team_id': team_ids[1], 'home_provider_team_url': team_urls[0],
        'away_provider_team_url': team_urls[1], 'season': '2026-2027',
        'date_local': local_date.isoformat(), 'date_year_inferred_from_season': True,
        'date_year_context': 'EXACT_SEASON_TABLE_JULY_JUNE_LOCAL_DATE_ONLY',
        'display_score': score, 'interim_display_score': interim,
        'display_field': 'finalresult', 'candidate_only': True,
        'completion_status_unverified': True, 'result_period_unverified': True,
        'independently_verified': False, 'eligible_for_model_scoring': False,
    }


def parse_html(raw):
    """Return quarantined observations and row diagnostics; source is not verified."""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError('INVALID_OR_OVERSIZED_NDR_HTML')
    try:
        html = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise ValueError('INVALID_NDR_HTML_ENCODING') from exc
    parser = _ResultsParser()
    parser.feed(html)
    parser.close()
    if parser.stack or len(parser.tables) != 1:
        raise ValueError('MISSING_OR_UNCLOSED_RESULTS_TABLE')
    rows = parser.tables[0].descendants('tr', 'sport-match')
    if not rows or len(rows) > MAX_ROWS:
        raise ValueError('INVALID_RESULT_ROW_COUNT')
    observations, rejected = [], []
    fixture_ids, team_dates = set(), set()
    # A malformed duplicate must not hide a conflict with an accepted row.
    raw_fixture_ids = set()
    for row in rows:
        ids = [match.group(1) for anchor in row.descendants('a')
               if (match := FIXTURE_PATH.fullmatch(anchor.attrs.get('href', '')))]
        for fixture_id in ids:
            if fixture_id in raw_fixture_ids:
                raise ValueError('DUPLICATE_OR_CONFLICTING_RESULT_IDENTITY')
            raw_fixture_ids.add(fixture_id)
    for index, row in enumerate(rows, 1):
        try:
            observation = _row_observation(row)
        except ValueError as exc:
            rejected.append({'row_number': index, 'reason': str(exc)})
            continue
        fixture_id = observation['provider_fixture_id']
        identity = (observation['date_local'], *sorted((observation['home_provider_team_id'], observation['away_provider_team_id'])))
        if fixture_id in fixture_ids or identity in team_dates:
            raise ValueError('DUPLICATE_OR_CONFLICTING_RESULT_IDENTITY')
        fixture_ids.add(fixture_id)
        team_dates.add(identity)
        observations.append(observation)
    return observations, rejected


def _checked_path(path):
    path = Path(path).absolute()
    for component in [path, *path.parents]:
        if component.is_symlink():
            raise ValueError('SYMLINK_EVIDENCE_PATH')
    return path.resolve(strict=False)


def _read_file(path, maximum):
    path = _checked_path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > maximum or info.st_nlink != 1:
        raise ValueError('INVALID_EVIDENCE_FILE')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if not raw or len(raw) > maximum:
        raise ValueError('INVALID_EVIDENCE_FILE')
    return raw


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_MANIFEST_KEY')
        result[key] = value
    return result


def _capture(value, now):
    if not isinstance(value, str):
        raise ValueError('INVALID_CAPTURE_TIME')
    try:
        captured = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('INVALID_CAPTURE_TIME') from exc
    if captured.tzinfo is None or captured.utcoffset().total_seconds() != 0 or captured > now:
        raise ValueError('INVALID_OR_FUTURE_CAPTURE_TIME')
    return captured.isoformat()


def _safe_report():
    return {'schema': 'football-king-ndr-result-observations-v1',
            'status': 'HOLD', 'production_recommendations': 'DISABLED',
            'candidate_only': True, 'independently_verified': False,
            'eligible_for_model_scoring': False, 'completion_status_unverified': True,
            'result_period_unverified': True, 'observation_count': 0,
            'observations': [], 'rejected_row_count': 0, 'rejected_rows': [],
            'limitations': ['SOURCE_BYTES_AND_CAPTURE_METADATA_NOT_INDEPENDENTLY_AUTHENTICATED',
                            'FINALRESULT_CLASS_DOES_NOT_PROVE_MATCH_COMPLETION_OR_90_MINUTE_PERIOD',
                            'NO_LINK_TO_SEALED_FORECAST_IDENTITIES_OR_MODEL_SCORING']}


def _policy_index_files(folder, manifest):
    """New policy captures contain no DFB bytes, including unlisted files.

    Historical directories retain their original interpretation. The v3
    manifest itself is validated separately before its contents are trusted.
    """
    if manifest.get('schema') != 'football-king-external-raw-evidence-v3':
        return
    sources = manifest.get('sources')
    if not isinstance(sources, list) or len(sources) != 2 or not isinstance(sources[1], dict):
        raise ValueError('INVALID_INDEX_ORIGIN_PROVIDER_ORDER')
    expected = {'manifest.json'}
    if sources[1].get('status') == 'FETCHED_UNVERIFIED':
        expected.add('ndr.html')
    if {path.name for path in folder.iterdir()} != expected:
        raise ValueError('UNLISTED_POLICY_INDEX_RAW_BYTES')


def observe(raw_dir, now=None):
    """Validate collector evidence integrity and parse display candidates offline."""
    folder = _checked_path(raw_dir)
    if not folder.is_dir():
        raise ValueError('INVALID_RAW_DIRECTORY')
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ValueError('INVALID_CURRENT_TIME')
    try:
        manifest = json.loads(_read_file(folder / 'manifest.json', MAX_MANIFEST_BYTES), object_pairs_hook=_json_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('INVALID_MANIFEST_JSON') from exc
    if not isinstance(manifest, dict) or manifest.get('schema') not in ('football-king-external-raw-evidence-v1', 'football-king-external-raw-evidence-v2', 'football-king-external-raw-evidence-v3') or manifest.get('status') != 'HOLD' or manifest.get('production_recommendations') != 'DISABLED' or manifest.get('independently_verified') is not False or manifest.get('eligible_for_model_scoring') is not False:
        raise ValueError('UNSAFE_COLLECTOR_MANIFEST')
    if manifest['schema'] in ('football-king-external-raw-evidence-v2', 'football-king-external-raw-evidence-v3'):
        if __package__:
            from .index_origin_metadata import validate_manifest
        else:
            from index_origin_metadata import validate_manifest
        validate_manifest(manifest, now=current)
    _policy_index_files(folder, manifest)
    captured = _capture(manifest.get('captured_utc'), current)
    sources = manifest.get('sources')
    if not isinstance(sources, list) or len(sources) > 8 or not all(isinstance(source, dict) for source in sources):
        raise ValueError('INVALID_MANIFEST_SOURCES')
    ndr_sources = [source for source in sources if source.get('provider') == 'NDR']
    if len(ndr_sources) > 1:
        raise ValueError('NDR_SOURCE_MISSING_OR_AMBIGUOUS')
    if not ndr_sources:
        report = _safe_report()
        report.update(source_available=False, source_unavailable_reason='NDR_SOURCE_NOT_AVAILABLE', captured_utc=captured)
        return report
    source = ndr_sources[0]
    if source.get('source_url') != SOURCE_URL:
        raise ValueError('INVALID_NDR_SOURCE_METADATA')
    if source.get('status') == 'ERROR':
        report = _safe_report()
        report.update(source_available=False, source_unavailable_reason='NDR_SOURCE_NOT_AVAILABLE', captured_utc=captured)
        return report
    if source.get('status') != 'FETCHED_UNVERIFIED' or source.get('raw_file') != 'ndr.html' or type(source.get('http_status')) is not int or source['http_status'] != 200:
        raise ValueError('INVALID_NDR_SOURCE_METADATA')
    digest = source.get('raw_sha256')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('INVALID_RAW_SHA256')
    raw = _read_file(folder / 'ndr.html', MAX_BYTES)
    if type(source.get('bytes')) is not int or source['bytes'] != len(raw) or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('RAW_SIZE_OR_HASH_MISMATCH')
    observations, rejected = parse_html(raw)
    provenance = {'provider': 'NDR', 'source_url': SOURCE_URL, 'raw_file': 'ndr.html',
                  'raw_sha256': digest, 'bytes': len(raw), 'captured_utc': captured,
                  'capture_time_independently_authenticated': False,
                  'source_identity_independently_authenticated': False}
    if manifest['schema'] in ('football-king-external-raw-evidence-v2', 'football-king-external-raw-evidence-v3'):
        provenance['index_manifest_schema'] = manifest['schema']
        provenance['index_origin_receipt'] = {key: source[key] for key in (
            'source_url', 'final_url', 'redirect_policy', 'requested_utc', 'completed_utc',
            'http_status', 'content_type')}
    for observation in observations:
        observation.update(source_url=SOURCE_URL, raw_sha256=digest, captured_utc=captured)
    report = _safe_report()
    report.update(source_available=True, source=provenance, observations=observations, observation_count=len(observations),
                  rejected_rows=rejected, rejected_row_count=len(rejected))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = _safe_report()
    exit_code = 0
    try:
        report = observe(args.raw_dir)
    except (OSError, ValueError, TypeError, RecursionError):
        # Do not expose arbitrary paths, parser excerpts or untrusted source data.
        report['error'] = 'NDR_OBSERVATION_INPUT_REJECTED'
        exit_code = 1
    output = _checked_path(args.output)
    # Input may have been rejected for a symlink; still emit a safe report to
    # an independently validated output path outside both lexical/resolved input.
    raw_dir = Path(args.raw_dir).absolute()
    resolved_raw_dir = raw_dir.resolve()
    if output == raw_dir or raw_dir in output.parents or output == resolved_raw_dir or resolved_raw_dir in output.parents:
        raise ValueError('OUTPUT_MUST_NOT_MODIFY_RAW_EVIDENCE')
    if output.exists() and (not output.is_file() or output.stat().st_nlink != 1):
        raise ValueError('INVALID_OUTPUT_FILE')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'HOLD', 'observation_count': report['observation_count'],
                      'rejected_row_count': report['rejected_row_count'], 'eligible_for_model_scoring': False}))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
