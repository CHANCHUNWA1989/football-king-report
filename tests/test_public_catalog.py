import json
import unittest
from research_quality.public_catalog import parse_catalog, MAX_BYTES

class CatalogTests(unittest.TestCase):
    def test_catalog(self):
        data = {"leagues":[{"idLeague":"42","strLeague":"Example League","strSport":"Soccer"},{"idLeague":"99","strLeague":"Other","strSport":"Other"}]}
        result = parse_catalog(json.dumps(data).encode())
        self.assertEqual(result, [{"id":"42","name":"Example League"}])
    def test_malformed(self):
        with self.assertRaises((ValueError, TypeError)):
            parse_catalog(b'[]')
    def test_size_cap(self):
        with self.assertRaises(ValueError):
            parse_catalog(b'x' * (MAX_BYTES + 1))
