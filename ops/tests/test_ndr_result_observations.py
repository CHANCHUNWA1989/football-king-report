"""NDR display observations must remain separate from authenticated FT outcomes."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ops.ndr_result_observations import observe, parse_html, SOURCE_URL

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


def row(fixture='5884', home='264', away='110', date='16.10.', score='1:0', interim='(0:0)'):
    return f'''<tr class="sport-match"><td headers="results-col-1"><span class="date">{date}</span><div class="time">20:30</div></td>
<td headers="results-col-2"><div class="teamwrapper"><a href="/sport/ergebnisse/fussballmaenner-486~_gameplan-mannschaftfussball{home}.html"><div class="teamname"><span class="nb-xs">Home</span><span class="ob-xs">H</span></div></a></div>
<div class="teamwrapper"><a href="/sport/ergebnisse/fussballmaenner-486~_gameplan-mannschaftfussball{away}.html"><div class="teamname"><span class="nb-xs">Away</span><span class="ob-xs">A</span></div></a></div></td>
<td class="erg" headers="results-col-3"><span class="finalresult">{score}</span><span class="interimresult">{interim}</span></td>
<td headers="results-col-4"><a href="https://www.ndr.de/sport/ergebnisse/spielstatistik-{fixture}.html">Ticker</a></td></tr>'''


def page(rows=None, summary='Fußball, Männer, Bundesliga, 2026-2027'):
    return f'<html><body><table class="datatable small results" summary="{summary}"><thead><tr><th>Date</th></tr></thead><tbody>{row() if rows is None else rows}</tbody></table></body></html>'.encode()


class NDRResultObservationTests(unittest.TestCase):
    def make_source(self, folder, body=None):
        body = page() if body is None else body
        (folder / 'ndr.html').write_bytes(body)
        manifest = {
            'schema': 'football-king-external-raw-evidence-v1',
            'captured_utc': '2026-10-18T17:56:00+00:00',
            'status': 'HOLD', 'production_recommendations': 'DISABLED',
            'independently_verified': False, 'eligible_for_model_scoring': False,
            'sources': [{'provider': 'NDR', 'source_url': SOURCE_URL,
                         'status': 'FETCHED_UNVERIFIED', 'raw_file': 'ndr.html',
                         'raw_sha256': hashlib.sha256(body).hexdigest(),
                         'bytes': len(body), 'http_status': 200, 'content_type': 'text/html'}]}
        self.write_manifest(folder, manifest)
        return manifest

    def write_manifest(self, folder, manifest):
        (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def test_exact_row_score_is_not_time_or_interim_and_never_ft(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.make_source(folder)
            report = observe(folder, now=NOW)
        self.assertEqual(report['observation_count'], 1)
        got = report['observations'][0]
        self.assertEqual(got['display_score'], {'home': 1, 'away': 0})
        self.assertEqual(got['interim_display_score'], {'home': 0, 'away': 0})
        self.assertEqual(got['provider_fixture_id'], '5884')
        self.assertEqual((got['home_provider_team_id'], got['away_provider_team_id']), ('264', '110'))
        self.assertEqual(got['date_local'], '2026-10-16')
        self.assertTrue(got['completion_status_unverified'])
        self.assertTrue(got['result_period_unverified'])
        self.assertTrue(got['candidate_only'])
        self.assertFalse(got['independently_verified'])
        self.assertFalse(got['eligible_for_model_scoring'])
        self.assertEqual(report['status'], 'HOLD')
        self.assertEqual(report['production_recommendations'], 'DISABLED')
        self.assertNotIn('ft', got)
        self.assertNotIn('y', got)
        self.assertNotIn('kickoff_utc', got)
        self.assertEqual(got['raw_sha256'], report['source']['raw_sha256'])

    def test_season_context_january_july_and_leap_validation(self):
        self.assertEqual(parse_html(page(row(date='10.01.')))[0][0]['date_local'], '2027-01-10')
        self.assertEqual(parse_html(page(row(date='10.07.')))[0][0]['date_local'], '2026-07-10')
        for invalid in ['29.02.', '31.04.', '16.10.2025', '16.10. 17.10.']:
            with self.subTest(invalid=invalid):
                obs, rejected = parse_html(page(row(date=invalid)))
                self.assertEqual(obs, [])
                self.assertEqual(len(rejected), 1)

    def test_rows_cannot_supply_each_others_missing_evidence(self):
        first = row().replace('<span class="finalresult">1:0</span>', '')
        second = row(fixture='5946', home='2574', away='220').replace('<span class="date">16.10.</span>', '')
        obs, rejected = parse_html(page(first + second))
        self.assertEqual(obs, [])
        self.assertEqual(len(rejected), 2)

    def test_missing_provider_ids_are_quarantined_not_name_matched(self):
        broken = row().replace('fussballmaenner-486~_gameplan-mannschaftfussball264.html', 'sport-report-264.html')
        obs, rejected = parse_html(page(broken))
        self.assertEqual(obs, [])
        self.assertEqual(rejected[0]['reason'], 'TEAM_IDENTITY_MISSING_OR_AMBIGUOUS')

    def test_ambiguous_teams_scores_date_and_details_are_quarantined(self):
        attacks = [
            row(away='264'),
            row().replace('</td>', '<span class="date">17.10.</span></td>', 1),
            row().replace('<span class="finalresult">1:0</span>', '<span class="finalresult">1:0</span><span class="finalresult">2:0</span>'),
            row().replace('Ticker</a>', 'Ticker</a><a href="https://www.ndr.de/sport/ergebnisse/spielstatistik-999.html">Ticker</a>'),
            row().replace('https://www.ndr.de/sport/ergebnisse/spielstatistik-5884.html', 'https://evil.example/sport/ergebnisse/spielstatistik-5884.html'),
            row().replace('fussballmaenner-486~_gameplan-mannschaftfussball264.html', 'fussballmaenner-486~_gameplan-mannschaftfussball264.html?x=1'),
        ]
        for attack in attacks:
            with self.subTest(attack=attack):
                obs, rejected = parse_html(page(attack))
                self.assertEqual(obs, [])
                self.assertEqual(len(rejected), 1)

    def test_strict_scores_and_script_or_live_markers(self):
        for score in ['31:0', '-1:0', '1:0 2:1', 'true:0', '1.0:0', '1:0 n.V.', '<script>1:0</script>', '<b>1:0</b>', '1:0 Live']:
            with self.subTest(score=score):
                self.assertEqual(parse_html(page(row(score=score)))[0], [])
        self.assertEqual(parse_html(page(row(score='30:30')))[0][0]['display_score'], {'home': 30, 'away': 30})
        self.assertEqual(parse_html(page(row().replace('Ticker</a>', 'Live 75. Minute</a>')))[0], [])

    def test_live_row_class_date_cell_status_and_malformed_parent_rejected(self):
        for body in [row().replace('class="sport-match"', 'class="sport-match live"'),
                     row().replace('<span class="date">16.10.</span>', '<span class="date">16.10.</span><span>Live 75. Minute</span>')]:
            with self.subTest(body=body):
                self.assertEqual(parse_html(page(body))[0], [])
        with self.assertRaisesRegex(ValueError, 'PARENT'):
            parse_html(page('<div>' + row() + '</div>'))

    def test_duplicate_fixture_or_reversed_same_fixture_rejected(self):
        for rows in [row() + row(), row() + row(score='2:0'), row() + row(fixture='999'), row() + row(fixture='999', home='110', away='264')]:
            with self.subTest(rows=rows):
                with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
                    parse_html(page(rows))

    def test_nested_or_malformed_html_and_tables_fail_closed(self):
        for body in [page(row().replace('<td headers="results-col-1">', '<td headers="results-col-1"><tr>')),
                     page(row().replace('</span><div class="time">', '</div><div class="time">', 1)),
                     page().replace(b'</table>', b''),
                     page(page().decode()),
                     page().replace(b'class="finalresult"', b'class="finalresult" class="interimresult"'),
                     page() + page(),
                     page(summary='Fußball, Männer, Bundesliga, 2025-2026')]:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    parse_html(body)

    def test_inert_results_tables_are_never_visible_observations(self):
        for tag in ['template', 'noscript', 'svg', 'math', 'iframe', 'object']:
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    parse_html(b'<' + tag.encode() + b'>' + page() + b'</' + tag.encode() + b'>')
        # HTMLParser handles script/style raw text without interpreting its tags.
        for tag in ['script', 'style']:
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    parse_html(b'<' + tag.encode() + b'>' + page() + b'</' + tag.encode() + b'>')

    def test_inert_containers_inside_score_row_are_quarantined(self):
        for tag in ['script', 'style', 'template', 'noscript', 'svg', 'math', 'iframe', 'object']:
            with self.subTest(tag=tag):
                body = row().replace('<span class="finalresult">1:0</span>', f'<{tag}><span class="finalresult">1:0</span></{tag}>')
                obs, rejected = parse_html(page(body))
                self.assertEqual(obs, [])
                self.assertEqual(len(rejected), 1)

    def test_non_void_self_closing_inert_tags_never_expose_results(self):
        for tag in ['script', 'style', 'template', 'noscript', 'svg', 'math', 'iframe', 'object', 'xmp', 'plaintext']:
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    parse_html(b'<' + tag.encode() + b'/>' + page())
        with self.assertRaises(ValueError):
            parse_html(page(row().replace('<span class="finalresult">1:0</span>', '<span class="finalresult"/>1:0')))

    def test_manifest_safety_and_capture_time_fail_closed(self):
        changes = [
            ('captured_utc', '2026-10-20T00:00:00Z'),
            ('captured_utc', '2026-10-18T17:56:00'),
            ('captured_utc', '2026-10-18T18:56:00+01:00'),
            ('captured_utc', None), ('schema', 'anything'),
            ('independently_verified', True), ('eligible_for_model_scoring', True),
            ('production_recommendations', 'ENABLED'), ('status', 'READY')]
        for key, value in changes:
            with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                manifest = self.make_source(folder)
                manifest[key] = value
                self.write_manifest(folder, manifest)
                with self.assertRaises(ValueError):
                    observe(folder, now=NOW)

    def test_source_url_path_hash_status_size_and_unique_provider(self):
        changes = [('source_url', SOURCE_URL + '?x=1'), ('source_url', SOURCE_URL.replace('www.ndr.de', 'evil.example')),
                   ('raw_file', '../ndr.html'), ('raw_file', '/tmp/ndr.html'),
                   ('raw_sha256', '0' * 64), ('raw_sha256', True),
                   ('bytes', True), ('bytes', 0), ('http_status', True), ('http_status', 201),
                   ('status', 'VERIFIED')]
        for key, value in changes:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                manifest = self.make_source(folder)
                manifest['sources'][0][key] = value
                self.write_manifest(folder, manifest)
                with self.assertRaises(ValueError):
                    observe(folder, now=NOW)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = self.make_source(folder)
            manifest['sources'].append(dict(manifest['sources'][0]))
            self.write_manifest(folder, manifest)
            with self.assertRaises(ValueError):
                observe(folder, now=NOW)

    def test_symlink_raw_manifest_and_ancestors_rejected(self):
        for name in ['ndr.html', 'manifest.json']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                folder = root / 'raw'
                folder.mkdir()
                self.make_source(folder)
                original = folder / name
                original.rename(root / name)
                original.symlink_to(root / name)
                with self.assertRaises(ValueError):
                    observe(folder, now=NOW)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'raw'
            folder.mkdir()
            self.make_source(folder)
            (root / 'linked').symlink_to(folder, target_is_directory=True)
            with self.assertRaises(ValueError):
                observe(root / 'linked', now=NOW)

    def test_audio_action_is_not_match_status_and_other_links_remain_rejected(self):
        audio = '<a href="https://www.sportschau.de/fussball/bundesliga/audio-100.html"><span class="icon icon-audio"></span>Audio Live</a>'
        body = row().replace('Ticker</a>', 'Ticker</a>' + audio)
        self.assertEqual(len(parse_html(page(body))[0]), 1)
        malicious = body.replace('https://www.sportschau.de/', 'https://evil.example/')
        self.assertEqual(parse_html(page(malicious))[0], [])
        ambiguous = body.replace('audio-100.html', 'spielstatistik-999.html').replace('www.sportschau.de', 'www.ndr.de')
        self.assertEqual(parse_html(page(ambiguous))[0], [])

    def test_unavailable_source_is_empty_hold_without_reading_stale_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = self.make_source(folder)
            manifest['sources'][0] = {'provider': 'NDR', 'source_url': SOURCE_URL, 'status': 'ERROR', 'error_type': 'TimeoutError'}
            self.write_manifest(folder, manifest)
            (folder / 'ndr.html').write_bytes(b'stale invalid bytes ignored')
            report = observe(folder, now=NOW)
            self.assertEqual(report['observations'], [])
            self.assertFalse(report['source_available'])
            self.assertEqual(report['source_unavailable_reason'], 'NDR_SOURCE_NOT_AVAILABLE')
            manifest['sources'] = []
            self.write_manifest(folder, manifest)
            self.assertEqual(observe(folder, now=NOW)['observations'], [])

    def test_malformed_duplicate_row_cannot_hide_identity_conflict(self):
        broken = row().replace('<span class="finalresult">1:0</span>', '')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            parse_html(page(row() + broken))

    def test_bounded_raw_bytes_bad_encoding_and_json_duplicates(self):
        for body in [b'x' * 3_000_001, b'\xff']:
            with self.subTest(size=len(body)), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                self.make_source(folder, body)
                with self.assertRaises(ValueError):
                    observe(folder, now=NOW)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.make_source(folder)
            original = (folder / 'manifest.json').read_text()
            (folder / 'manifest.json').write_text(original.replace('{', '{"status":"HOLD",', 1))
            with self.assertRaises(ValueError):
                observe(folder, now=NOW)

    def test_cli_refuses_evidence_alias_and_hardlinks_without_modifying_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / 'raw'
            raw.mkdir()
            self.make_source(raw)
            original = (raw / 'ndr.html').read_bytes()
            (root / 'alias.html').hardlink_to(raw / 'ndr.html')
            cases = [(str(raw / '..' / 'raw'), str(raw / 'ndr.html')),
                     (str(raw), str(root / 'alias.html'))]
            for raw_arg, output_arg in cases:
                with self.subTest(output=output_arg):
                    result = subprocess.run([sys.executable, '-m', 'ops.ndr_result_observations', '--raw-dir', raw_arg, '--output', output_arg], capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual((raw / 'ndr.html').read_bytes(), original)

    def test_cli_unavailable_source_does_not_fail_daily_research(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / 'raw'
            raw.mkdir()
            manifest = self.make_source(raw)
            manifest['sources'][0] = {'provider': 'NDR', 'source_url': SOURCE_URL, 'status': 'ERROR'}
            self.write_manifest(raw, manifest)
            output = root / 'result.json'
            result = subprocess.run([sys.executable, '-m', 'ops.ndr_result_observations', '--raw-dir', str(raw), '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            report = json.loads(output.read_text())
            self.assertFalse(report['source_available'])
            self.assertEqual(report['observations'], [])

    def test_cli_emits_safe_failure_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / 'raw'
            raw.mkdir()
            self.make_source(raw)
            (raw / 'ndr.html').write_bytes(b'changed')
            output = root / 'result.json'
            result = subprocess.run([sys.executable, '-m', 'ops.ndr_result_observations', '--raw-dir', str(raw), '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            report = json.loads(output.read_text())
            self.assertEqual(report['observations'], [])
            self.assertEqual(report['status'], 'HOLD')
            self.assertFalse(report['independently_verified'])
            self.assertFalse(report['eligible_for_model_scoring'])
            self.assertIn('error', report)


if __name__ == '__main__':
    unittest.main()
