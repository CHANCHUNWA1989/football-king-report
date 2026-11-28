"""Synthetic request policy only: no sockets, DNS, proxy or provider access."""
import unittest

RESOURCES = {
    'football': {'league-history': b'synthetic-league-fixture',
                 'score-history': b'synthetic-score-fixture'},
    'quant': {'fx-reference': b'synthetic-fx-fixture'},
}


def request(domain, method, path, headers, body):
    """Return an immutable fixture only; reject arbitrary destinations and bodies."""
    if type(domain) is not str or domain not in RESOURCES:
        raise ValueError('unknown domain')
    if type(method) is not str or method != 'GET':
        raise ValueError('method denied')
    if type(path) is not str or not path.startswith('/fixture/'):
        raise ValueError('path denied')
    resource = path[len('/fixture/'):]
    if resource not in RESOURCES[domain]:
        raise ValueError('resource denied')
    if type(headers) is not dict or headers != {'accept': 'application/octet-stream'}:
        raise ValueError('headers denied')
    if type(body) is not bytes or body != b'':
        raise ValueError('body denied')
    return {'body': RESOURCES[domain][resource], 'synthetic_only': True,
            'provider_egress_tested': False, 'egress_allowlist_verified': False,
            'network_rehearsal_allowed': False, 'status': 'HOLD',
            'model_input_allowed': False, 'live_trading': 'DISABLED',
            'production_recommendations': 'DISABLED'}


class Tests(unittest.TestCase):
    def call(self, **overrides):
        args = dict(domain='football', method='GET', path='/fixture/league-history',
                    headers={'accept': 'application/octet-stream'}, body=b'')
        args.update(overrides)
        return request(**args)

    def test_exact_fixture(self):
        r = self.call()
        self.assertEqual(r['body'], b'synthetic-league-fixture')
        self.assertIs(r['synthetic_only'], True)
        for k in ('provider_egress_tested', 'egress_allowlist_verified',
                  'network_rehearsal_allowed', 'model_input_allowed'):
            self.assertIs(r[k], False)
        self.assertEqual(r['status'], 'HOLD')
        self.assertEqual(r['live_trading'], 'DISABLED')
        self.assertEqual(r['production_recommendations'], 'DISABLED')

    def test_quant_fixture(self):
        self.assertEqual(self.call(domain='quant', path='/fixture/fx-reference')['body'], b'synthetic-fx-fixture')

    def test_cross_domain(self):
        with self.assertRaises(ValueError): self.call(domain='quant')

    def test_methods(self):
        for method in ('CONNECT', 'POST', 'HEAD', 'get', None):
            with self.subTest(method=method), self.assertRaises(ValueError): self.call(method=method)

    def test_paths(self):
        for path in ('https://example.com/', '//example.com/', '/fixture/../league-history',
                     '/fixture/%6ceague-history', '/fixture/league-history?host=x',
                     '/fixture/league-history#x', '/fixture/league-history/','/fixture/unknown'):
            with self.subTest(path=path), self.assertRaises(ValueError): self.call(path=path)

    def test_headers(self):
        for name in ('host', 'authorization', 'proxy-authorization', 'forwarded', 'x-forwarded-host', 'transfer-encoding'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.call(headers={'accept': 'application/octet-stream', name: 'fixture'})

    def test_body(self):
        for body in (b'x', '', None, bytearray()):
            with self.subTest(body=body), self.assertRaises(ValueError): self.call(body=body)

    def test_invalid_domain(self):
        for domain in ('production', '', None, []):
            with self.subTest(domain=domain), self.assertRaises(ValueError): self.call(domain=domain)


if __name__ == '__main__':
    unittest.main(verbosity=2)
