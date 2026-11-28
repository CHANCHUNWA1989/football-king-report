"""Preflight for existing historical qualification only; never approve live sources."""
import argparse
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

MAX_CONFIG_BYTES = 4096
ROOT = Path(__file__).resolve().parent
DOMAINS = frozenset(('football', 'quant'))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate config key')
        result[key] = value
    return result


def check(domain, path):
    report = {'domain': domain, 'status': 'HOLD', 'live_trading': 'DISABLED',
              'production_recommendations': 'DISABLED', 'model_input_allowed': False,
              'live_source_count': 0, 'historical_only': True,
              'independent_upstream_certified': False,
              'historical_preflight_pass': False}
    try:
        if domain not in DOMAINS:
            raise ValueError('unknown domain')
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_CONFIG_BYTES + 1)
        if len(raw) > MAX_CONFIG_BYTES:
            raise ValueError('oversized config')
        doc = json.loads(raw, object_pairs_hook=unique_object)
        if (type(doc) is not dict or set(doc) != {'enabled', 'sources'}
                or doc['enabled'] is not False or type(doc['sources']) is not list
                or doc['sources']):
            raise ValueError('live config must be exactly disabled and empty')
        report['historical_preflight_pass'] = True
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        report['error_type'] = type(exc).__name__
    return report


class Tests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'config.json'

    def assess(self, raw, domain='football'):
        self.path.write_bytes(raw)
        return check(domain, self.path)

    def test_both_domains(self):
        for domain in DOMAINS:
            r = self.assess(b'{"enabled":false,"sources":[]}', domain)
            self.assertTrue(r['historical_preflight_pass'])
            self.assertEqual(r['live_source_count'], 0)
            self.assertEqual(r['status'], 'HOLD')
            self.assertFalse(r['model_input_allowed'])

    def test_enabled(self):
        self.assertFalse(self.assess(b'{"enabled":true,"sources":[]}')['historical_preflight_pass'])

    def test_nonempty(self):
        self.assertFalse(self.assess(b'{"enabled":false,"sources":[{"approved":true}]}')['historical_preflight_pass'])

    def test_integer_false(self):
        self.assertFalse(self.assess(b'{"enabled":0,"sources":[]}')['historical_preflight_pass'])

    def test_duplicate(self):
        self.assertFalse(self.assess(b'{"enabled":true,"enabled":false,"sources":[]}')['historical_preflight_pass'])

    def test_extra_key(self):
        self.assertFalse(self.assess(b'{"enabled":false,"sources":[],"allow_live":true}')['historical_preflight_pass'])

    def test_missing(self):
        self.assertFalse(check('football', self.path)['historical_preflight_pass'])

    def test_oversize(self):
        self.assertFalse(self.assess(b' ' * 4097)['historical_preflight_pass'])

    def test_unknown_domain(self):
        self.assertFalse(self.assess(b'{"enabled":false,"sources":[]}', 'other')['historical_preflight_pass'])

    def test_malformed(self):
        self.assertFalse(self.assess(b'{')['historical_preflight_pass'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--domain', choices=sorted(DOMAINS))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.self_test:
        unittest.main(argv=['source_preflight'], verbosity=2)
    if args.domain is None or args.output is None:
        parser.error('--domain and --output required')
    report = check(args.domain, ROOT / 'disabled.json')
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    raise SystemExit(0 if report['historical_preflight_pass'] else 2)
