import sys
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_historical_smoke import fetch,ROOT,IDS,MAX_BYTES,INDEX_LIMIT,GROUP_IDS
from live_core_multi_source import NoRedirect

class HistoricalSmokeNetworkBoundsTests(unittest.TestCase):
    def test_registered_paths_only(self):
        with patch("deep_handicap_historical_smoke.build_opener") as opener:
            for path,limit in (("../README.md",MAX_BYTES),("data/events/999.json",MAX_BYTES),
                               ("data/matches/43/106.json",MAX_BYTES),
                               (f"data/events/{IDS[0]}.json",True)):
                with self.assertRaises(ValueError):fetch(path,limit)
            opener.assert_not_called()
    def test_bounded_response_no_redirect_handler(self):
        path="data/matches/43/106.json"
        with patch("deep_handicap_historical_smoke.build_opener") as opener:
            response=opener.return_value.open.return_value.__enter__.return_value
            response.status=200
            response.geturl.return_value=ROOT+path
            response.read.return_value=b"[]"
            self.assertEqual(fetch(path,INDEX_LIMIT),b"[]")
            self.assertIsInstance(opener.call_args.args[0],NoRedirect)
            response.read.assert_called_once_with(INDEX_LIMIT+1)
            response.geturl.return_value="https://other.example/redirect"
            with self.assertRaises(ValueError):fetch(path,INDEX_LIMIT)
            response.geturl.return_value=ROOT+path
            response.status=206
            with self.assertRaises(ValueError):fetch(path,INDEX_LIMIT)
    def test_oversize_response_rejected(self):
        path="data/matches/43/106.json"
        with patch("deep_handicap_historical_smoke.build_opener") as opener:
            response=opener.return_value.open.return_value.__enter__.return_value
            response.status=200
            response.geturl.return_value=ROOT+path
            response.read.return_value=b"x"*(INDEX_LIMIT+1)
            with self.assertRaises(ValueError):fetch(path,INDEX_LIMIT)

    def test_full_group_allowlist_is_explicit_and_bounded(self):
        self.assertEqual(len(GROUP_IDS),48)
        path=f"data/events/{GROUP_IDS[0]}.json"
        with patch("deep_handicap_historical_smoke.build_opener") as opener:
            with self.assertRaises(ValueError):fetch(path,MAX_BYTES)
            with self.assertRaises(ValueError):fetch("data/events/3857302.json",MAX_BYTES,full_group=True)
            with self.assertRaises(ValueError):fetch(path,MAX_BYTES,full_group=1)
            opener.assert_not_called()
            response=opener.return_value.open.return_value.__enter__.return_value
            response.status=200
            response.geturl.return_value=ROOT+path
            response.read.return_value=b"[]"
            self.assertEqual(fetch(path,MAX_BYTES,full_group=True),b"[]")
            response.read.assert_called_once_with(MAX_BYTES+1)
