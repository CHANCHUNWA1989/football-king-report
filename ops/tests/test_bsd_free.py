"""BSD free market backups must pass strict time and credential containment."""
import copy,json,sys,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bsd_free import collect,parse_catalog,parse_fixtures,derive,read,stamp
from bsd_guard import validate,should_replace

NOW=datetime(2026,10,9,10,tzinfo=timezone.utc)
KICK=(NOW+timedelta(days=2)).isoformat()
QUOTE=(NOW-timedelta(minutes=40)).isoformat()

def bundle():
    leagues={"results":[{"id":77,"name":"Bundesliga","country":"Germany"},
                        {"id":78,"name":"Premier League","country":"England"}]}
    events={"results":[{"id":444,"league_id":77,"home_team":{"name":"Bayern Munich"},
                        "away_team":{"name":"Dortmund"},"status":"upcoming",
                        "start_time":KICK}]}
    odds={"results":[{"event_id":444,"market":"1x2","outcome":name,
                      "decimal_odds":price,"bookmaker_slug":"consensus",
                      "updated_at":QUOTE}
        for name,price in (("HOME",2.2),("DRAW",3.4),("AWAY",3.5))]}
    return leagues,events,odds

class Response:
    def __init__(self,body):self.content=body if isinstance(body, bytes) else json.dumps(body).encode()
    def read(self,n):return self.content[:n]
    def __enter__(self):return self
    def __exit__(self,*x):return False

class FreeBSDTests(unittest.TestCase):
    def setUp(self):
        self.urls=[]
        def api(req,timeout):
            self.urls.append(req)
            a,b,c=bundle()
            if "/leagues/" in req.full_url:return Response(a)
            if "/events/" in req.full_url:return Response(b)
            return Response(c)
        self.api=api

    def test_no_key_does_not_call_any_provider_or_fake_odds(self):
        out=collect(now=NOW,token="",client=self.api)
        self.assertEqual(out["status"],"NOT_CONFIGURED")
        self.assertEqual(self.urls,[])
        self.assertEqual(out["market_count"],0)
        self.assertEqual(out["requests_attempted"],0)
        self.assertEqual(validate(out,now=NOW),NOW)

    def test_one_3_request_transaction_has_1x2_consensus_derived_only(self):
        secret="SECRET-NEVER-COMMIT-42"
        out=collect(now=NOW,token=secret,client=self.api)
        self.assertEqual(out["requests_attempted"],3)
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        self.assertEqual(out["league_count"],2)
        self.assertEqual(out["fixture_count"],1)
        self.assertEqual(out["market_count"],1)
        self.assertEqual(validate(out,now=NOW),NOW)
        self.assertNotIn(secret,json.dumps(out))
        self.assertTrue(all("Authorization" in dict(q.header_items()) for q in self.urls))
        self.assertTrue(all(secret not in q.full_url for q in self.urls))
        self.assertNotIn("decimal_odds",json.dumps(out))
        self.assertFalse(out["replaces_current_market_automatically"])
        self.assertFalse(out["licensed_per_bookmaker_prices_available"])

    def test_ambiguous_vendor_bookmaker_slug_is_hold_not_consensus(self):
        """Duplicate raw bookmaker identity must not become allowed consensus."""
        a, b, c = bundle()
        raw = json.dumps(c)
        old = '"bookmaker_slug": "consensus"'
        self.assertIn(old, raw)
        raw = raw.replace(
            old, '"bookmaker_slug": "licensed_paid", "bookmaker_slug": "consensus"', 1
        )
        requests = []
        def api(req, timeout):
            requests.append(req.full_url)
            if "/leagues/" in req.full_url:
                return Response(a)
            if "/events/" in req.full_url:
                return Response(b)
            return Response(raw.encode("utf-8"))
        result = collect(now=NOW, token="synthetic-secret", client=api)
        self.assertEqual(len(requests), 3)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["warnings"], ["BSD_VENDOR_DUPLICATE_JSON_KEY"])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["market_count"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_vendor_nonfinite_unused_metadata_is_hold(self):
        """Even ignored vendor fields cannot introduce non-standard NaN JSON."""
        a, b, c = bundle()
        raw = json.dumps(c)
        old = '"decimal_odds": 2.2'
        self.assertIn(old, raw)
        raw = raw.replace(old, '"unused_metadata": NaN, ' + old, 1)
        def api(req, timeout):
            if "/leagues/" in req.full_url:
                return Response(a)
            if "/events/" in req.full_url:
                return Response(b)
            return Response(raw.encode("utf-8"))
        result = collect(now=NOW, token="synthetic-secret", client=api)
        self.assertEqual(result["requests_attempted"], 3)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["warnings"], ["BSD_VENDOR_NONFINITE_JSON"])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["market_count"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_unknown_leagues_are_not_guessed(self):
        self.assertEqual(parse_catalog({"results":[{"id":4,"name":"Premier League","country":"Scotland"}]}),{})

    def test_duplicate_league_id_cannot_rebind_event_identity(self):
        """The same vendor league ID must not silently change competition."""
        leagues, events, odds = bundle()
        leagues["results"].append({
            "id": 77, "name": "Premier League", "country": "England"
        })
        def api(req, timeout):
            if "/leagues/" in req.full_url:
                return Response(leagues)
            if "/events/" in req.full_url:
                return Response(events)
            return Response(odds)
        result = collect(now=NOW, token="synthetic-secret", client=api)
        self.assertEqual(result["requests_attempted"], 3)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["warnings"], ["BSD_UNVERIFIED_FIELD_FORMAT"])
        self.assertEqual(result["market_count"], 0)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_duplicate_event_id_cannot_rebind_team_or_kickoff(self):
        """Conflicting event IDs cannot silently overwrite 1X2 fixture."""
        leagues, events, odds = bundle()
        alternate = copy.deepcopy(events["results"][0])
        alternate["home_team"], alternate["away_team"] = (
            alternate["away_team"], alternate["home_team"]
        )
        alternate["start_time"] = (NOW + timedelta(days=3)).isoformat()
        events["results"].append(alternate)
        def api(req, timeout):
            if "/leagues/" in req.full_url:
                return Response(leagues)
            if "/events/" in req.full_url:
                return Response(events)
            return Response(odds)
        result = collect(now=NOW, token="synthetic-secret", client=api)
        self.assertEqual(result["requests_attempted"], 3)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["warnings"], ["BSD_UNVERIFIED_FIELD_FORMAT"])
        self.assertEqual(result["market_count"], 0)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_duplicate_event_id_with_ineligible_second_row_still_blocks(self):
        """A duplicate ID cannot hide behind an otherwise rejected row."""
        leagues, events, odds = bundle()
        alternate = copy.deepcopy(events["results"][0])
        alternate["status"] = "in_play"
        events["results"].append(alternate)
        self.assertRaisesRegex(
            ValueError, "BSD_DUPLICATE_EVENT_ID",
            parse_fixtures, events, parse_catalog(leagues), NOW
        )

    def test_same_team_alias_in_both_sides_must_hold_not_publish_consensus(self):
        """Distinct raw names can resolve to one canonical club identity."""
        leagues, fixtures, odds = bundle()
        fixtures["results"][0]["away_team"] = {"name": "FC Bayern München"}
        # Both spellings are curated Bayern aliases in the Bundesliga.
        self.assertNotEqual(
            fixtures["results"][0]["home_team"]["name"],
            fixtures["results"][0]["away_team"]["name"],
        )
        def api(req, timeout):
            if "/leagues/" in req.full_url:
                return Response(leagues)
            if "/events/" in req.full_url:
                return Response(fixtures)
            return Response(odds)
        result = collect(now=NOW, token="synthetic-secret", client=api)
        self.assertEqual(result["requests_attempted"], 3)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["warnings"], ["BSD_UNVERIFIED_FIELD_FORMAT"])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["market_count"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_alias_self_match_cannot_be_returned_as_valid_fixture(self):
        """Reject canonical collision before any odds/probabilities are derived."""
        leagues, fixtures, _ = bundle()
        fixtures["results"][0]["home_team"] = {"name": "Bayern Munich"}
        fixtures["results"][0]["away_team"] = {"name": "Bayern München"}
        with self.assertRaisesRegex(ValueError, "BSD_SELF_MATCH_CANONICAL_TEAM"):
            parse_fixtures(fixtures, parse_catalog(leagues), NOW)

    def test_market_requires_three_distinct_outcomes(self):
        a,b,c=bundle()
        leagues=parse_catalog(a)
        fixtures=parse_fixtures(b,leagues,NOW)
        self.assertEqual(len(fixtures),1)
        c["results"]=c["results"][:2]
        self.assertEqual(derive(c,fixtures,NOW),[])

    def test_duplicate_outcome_does_not_create_fake_price(self):
        a,b,c=bundle()
        c["results"].append(copy.deepcopy(c["results"][0]))
        self.assertEqual(derive(c,parse_fixtures(b,parse_catalog(a),NOW),NOW),[])

    def test_future_quote_and_inplay_are_discarded(self):
        a,b,c=bundle()
        c["results"][0]["updated_at"]=(NOW+timedelta(hours=2)).isoformat()
        self.assertEqual(derive(c,parse_fixtures(b,parse_catalog(a),NOW),NOW),[])
        c["results"][0]["updated_at"]=(NOW-timedelta(minutes=40)).isoformat()
        b["results"][0]["start_time"]=(NOW-timedelta(minutes=10)).isoformat()
        self.assertEqual(parse_fixtures(b,parse_catalog(a),NOW),{})

    def test_paid_rows_cannot_be_published(self):
        a,b,c=bundle()
        c["results"][0]["bookmaker_slug"]="real_paid_book"
        self.assertEqual(derive(c,parse_fixtures(b,parse_catalog(a),NOW),NOW),[])

    def test_wrong_market_margin_rejected(self):
        a,b,c=bundle()
        for row in c["results"]:row["decimal_odds"]=1.05
        self.assertEqual(derive(c,parse_fixtures(b,parse_catalog(a),NOW),NOW),[])

    def test_raw_price_in_public_research_rejected(self):
        doc=collect(now=NOW,token="secret",client=self.api)
        doc["events"][0]["decimal_odds"]=2.3
        with self.assertRaisesRegex(ValueError,"BSD_UNAUTHORIZED_RAW_MARKET_FIELDS"):
            validate(doc,now=NOW)

    def test_fake_value_betting_activation_rejected(self):
        doc=collect(now=NOW,token="secret",client=self.api)
        doc["replaces_current_market_automatically"]=True
        with self.assertRaisesRegex(ValueError,"BSD_UNSAFE_PROVENANCE"):
            validate(doc,now=NOW)

    def test_betting_quote_stamp_cannot_be_after_kickoff(self):
        doc=collect(now=NOW,token="secret",client=self.api)
        doc["events"][0]["market_last_update_utc"]=(NOW+timedelta(days=3)).isoformat()
        with self.assertRaisesRegex(ValueError,"BSD_MARKET_TIME_LEAKAGE"):
            validate(doc,now=NOW)

    def test_does_not_require_paid_endpoint_or_exceed_request_cap(self):
        collect(now=NOW,token="secret",client=self.api)
        self.assertEqual(len(self.urls),3)
        self.assertTrue(all("/api/v2/" in q.full_url for q in self.urls))
        self.assertTrue(all("best/" not in q.full_url for q in self.urls))

    def test_token_unauthorized_stops_immediately(self):
        tries=[]
        def reject(req,timeout):
            tries.append(req.full_url)
            raise HTTPError(req.full_url,401,"unauthorized",None,None)
        out=collect(now=NOW,token="secret",client=reject)
        self.assertEqual(len(tries),1)
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["warnings"],["BSD_ACCESS_REJECTED"])

    def test_no_expired_or_duplicate_archive_overwrite(self):
        now=datetime.now(timezone.utc)
        fresh=collect(now=now,token="",client=self.api)
        self.assertFalse(should_replace(fresh,fresh))
        old=copy.deepcopy(fresh)
        old["captured_utc"]=(now-timedelta(minutes=1)).isoformat()
        self.assertFalse(should_replace(old,fresh))
        self.assertTrue(should_replace(fresh,old))

if __name__=="__main__": unittest.main()
