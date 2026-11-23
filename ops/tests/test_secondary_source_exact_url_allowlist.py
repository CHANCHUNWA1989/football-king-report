"""No-network RED-first tests of the shared football source HTTP boundary.

Never use a real API key, origin, or live URL for these tests. The fixture
opener never performs HTTP; it records only synthetic, locally supplied data.
"""
import inspect
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import secondary_sources as ss
import research_extensions as ext


class FakeResponse:
    def __init__(self, data=None):
        self.payload = json.dumps(data if data is not None else {"ok": True}).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.payload[:size]


SYNTHETIC_HEADER = {"Authorization": "Bearer NOT_A_REAL_TOKEN"}


class SourceReadJsonExactURLTests(unittest.TestCase):
    def setUp(self):
        self.seen = []
    def fake(self, request, timeout):
        self.seen.append((request.full_url, dict(request.header_items())))
        return FakeResponse()

    def blocked(self, url, headers=None):
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_SOURCE_URL"):
            ss.read_json(url, headers or SYNTHETIC_HEADER, opener=self.fake)
        self.assertEqual(self.seen, [], "NO URL or header may be sent on rejection")

    def test_https_attacker_domain_must_not_receive_authorization(self):
        self.blocked("https://collector.example/receive?key=SYNTHETIC")

    def test_provider_hostname_suffix_is_not_same_host(self):
        self.blocked("https://api.football-data.org.attacker.example/v4/competitions/PL/matches?dateFrom=2026-10-08&dateTo=2026-10-16")
        self.blocked("https://api.sportmonks.com.attacker.example/v3/football/leagues/271")

    def test_userinfo_and_host_confusion_rejected_before_header_is_built(self):
        self.blocked("https://api.football-data.org@collector.example/v4/competitions/PL/matches?dateFrom=2026-10-08&dateTo=2026-10-16")
        self.blocked("https://foo@api.football-data.org/v4/competitions/PL/matches?dateFrom=2026-10-08&dateTo=2026-10-16")

    def test_https_nonstandard_port_and_embedded_fragment_rejected(self):
        self.blocked("https://api.football-data.org:444/v4/competitions/PL/matches?dateFrom=2026-10-08&dateTo=2026-10-16")
        self.blocked("https://api.football-data.org/v4/competitions/PL/matches?dateFrom=2026-10-08&dateTo=2026-10-16#secret")

    def test_encoded_path_and_dot_segment_traversal_rejected(self):
        self.blocked("https://api.football-data.org/v4/competitions/PL/../BL1/matches?dateFrom=2026-10-08&dateTo=2026-10-16")
        self.blocked("https://api.football-data.org/v4/competitions/%50L/matches?dateFrom=2026-10-08&dateTo=2026-10-16")
        self.blocked("https://api.football-data.org/v4/competitions/PL/matches/extra?dateFrom=2026-10-08&dateTo=2026-10-16")

    def test_unknown_api_football_odds_route_and_query_rejected(self):
        self.blocked("https://v3.football.api-sports.io/odds/live?league=39&season=2026")
        self.blocked("https://v3.football.api-sports.io/odds?league=39&season=2026&bet=1&page=2")
        self.blocked("https://v3.football.api-sports.io/odds?league=39&season=2026&bet=1&page=1&api_key=SYNTHETIC")

    def test_no_extra_or_duplicate_query_params(self):
        self.blocked("https://www.thesportsdb.com/api/v1/json/123/eventsday.php?d=2026-10-09&l=4328&token=private")
        self.blocked("https://www.thesportsdb.com/api/v1/json/123/eventsday.php?d=2026-10-09&l=4328&l=4329")

    def test_no_invalid_sportsdb_league_or_day(self):
        self.blocked("https://www.thesportsdb.com/api/v1/json/123/eventsday.php?d=not-a-date&l=4328")
        self.blocked("https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id=99999")

    def test_no_public_metadata_endpoint_assumed_safe_by_hostname(self):
        self.blocked("https://raw.githubusercontent.com/elsewhere/repo/main/secret")
        self.blocked("https://openfootapi.com/v1/account?token=synthetic")
        self.blocked("https://openfootapi.com/v1/matches?date=2026-10-09&key=synthetic")

    def test_reject_plain_http_or_pathless_root(self):
        self.blocked("http://v3.football.api-sports.io/fixtures?league=39&season=2026&next=3")
        self.blocked("https://v3.football.api-sports.io/")

    def test_authorized_six_league_sources_keep_working_without_real_http(self):
        good = [
            "https://www.thesportsdb.com/api/v1/json/123/eventsday.php?d=2026-10-09&l=4328",
            "https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id=4329",
            "https://www.thesportsdb.com/api/v1/json/123/eventspastleague.php?id=4335",
            "https://v3.football.api-sports.io/fixtures?league=39&season=2026&next=3",
            "https://v3.football.api-sports.io/odds?league=39&season=2026&bet=1&page=1",
            "https://api.football-data.org/v4/competitions/PL/matches?dateFrom=2026-10-08&dateTo=2026-10-16",
            "https://api.sportmonks.com/v3/football/leagues/271",
            "https://api.sportmonks.com/v3/football/leagues/501",
        ]
        for url in good:
            with self.subTest(url=url):
                self.assertEqual(ss.read_json(url, {}, opener=self.fake), {"ok": True})
        self.assertEqual([x[0] for x in self.seen], good)

    def test_authorized_research_extensions_keep_working(self):
        good = [
            ext.CATALOG,
            ext.OPENFOOT + "/v1/competitions",
            ext.OPENFOOT + "/v1/matches?date=2026-10-09",
        ]
        for url in good:
            self.assertEqual(ss.read_json(url, {}, opener=self.fake), {"ok": True})
        self.assertEqual([x[0] for x in self.seen], good)

    def test_request_has_no_headers_with_fake_https_attacker(self):
        result, reason = ss.fetch(
            "api_football", "https://private-data.example/exfil",
            {"x-apisports-key": "FAKE_NOT_A_SECRET"}, requester=self.fake
        )
        self.assertEqual((result, reason), (None, "INVALID_DATA"))
        self.assertEqual(self.seen, [])

    def test_direct_helper_default_must_not_bind_urlopen_redirect_follower(self):
        # No actual HTTP: inspect the signature only, so the old vulnerable
        # implementation can be RED-tested without contacting any service.
        default = inspect.signature(ss.read_json).parameters["opener"].default
        self.assertIsNone(default)

    def test_existing_fixed_sportsdb_collection_works_offline(self):
        # The 48-call free source loop must remain stable. All mocked.
        sample = ss.collect(
            now=datetime(2026, 10, 9, 8, tzinfo=timezone.utc),
            keys={}, requester=self.fake
        )
        self.assertEqual(len(self.seen), 48)
        self.assertEqual(sample["providers"][0]["calls_attempted"], 48)
        self.assertEqual(sample["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
