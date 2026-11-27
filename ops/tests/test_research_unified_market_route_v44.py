import json
import unittest
from datetime import timedelta,datetime,timezone
from pathlib import Path
from unittest.mock import patch
from ops.research_unified_market_route_v44 import route
from ops.tests.test_research_prospective_market_v41 import fixture as primary_fixture,NOW
from ops.tests.test_research_private_propline_v43 import fixture as private_fixture

def raw(x):return json.dumps(x).encode()
def backup():
    r=private_fixture()
    r["commence_time"]=(NOW+timedelta(hours=2)).isoformat()
    for b in r["bookmakers"]:
        b["markets"][0]["last_update"]=(NOW-timedelta(minutes=2)).isoformat()
    return r
def batch(r):
    return {"raw":raw({"events":[r]}),"league":"epl","captured_utc":NOW.isoformat()}
def primary():
    d=primary_fixture()
    r=d["events"][0]
    r["market_last_update_utc"]=(NOW-timedelta(minutes=5)).isoformat()
    r.update(p_home=.39,p_draw=.28,p_away=.33)
    return d
def run(p,b):
    with patch("ops.research_prospective_market_v41.REGISTRATION_NOT_BEFORE","2026-11-20T00:00:00Z"),patch("ops.research_unified_market_route_v44.REGISTRATION_NOT_BEFORE","2026-11-20T00:00:00Z"):
        return route(raw(p) if p is not None else None,b,as_of=NOW.isoformat())
class UnifiedMarketRouteTests(unittest.TestCase):
    def test_consistency_no_blend(self):
        c,r=run(primary(),[batch(backup())])
        self.assertEqual(r["route_states"],{"PRIMARY_WITH_BACKUP_CONSISTENCY":1})
        self.assertEqual(c[0]["component"]["market"]["p"],[.39,.28,.33])
        self.assertTrue(c[0]["private_only"])
        self.assertFalse(r["public_output_allowed"])
        self.assertNotIn("Arsenal",json.dumps(r))
    def test_private_only(self):
        c,r=run(None,[batch(backup())])
        self.assertEqual(r["route_states"],{"PRIVATE_BACKUP_ONLY":1})
        self.assertEqual(c[0]["component"]["market"]["source_id"],"propline:v1")
    def test_probability_conflict(self):
        p=primary();p["events"][0].update(p_home=.8,p_draw=.1,p_away=.1)
        c,r=run(p,[batch(backup())])
        self.assertEqual(c,[])
        self.assertEqual(r["route_states"],{"CROSS_SOURCE_PROBABILITY_CONFLICT":1})
    def test_schedule_conflict(self):
        b=backup();b["commence_time"]=(NOW+timedelta(hours=3)).isoformat()
        c,r=run(primary(),[batch(b)])
        self.assertEqual(c,[])
        self.assertEqual(r["route_states"],{"POSSIBLE_SCHEDULE_CONFLICT":2})
    def test_update_skew(self):
        p=primary();p["events"][0]["market_last_update_utc"]=(NOW-timedelta(minutes=30)).isoformat()
        c,r=run(p,[batch(backup())])
        self.assertEqual(c,[])
        self.assertEqual(r["route_states"],{"CROSS_SOURCE_UPDATE_SKEW":1})
    def test_duplicate_private_batch(self):
        b=batch(backup())
        with self.assertRaises(ValueError):run(None,[b,b])
    def test_stale_private_batch(self):
        b=batch(backup());b["captured_utc"]=(NOW-timedelta(minutes=21)).isoformat()
        c,r=run(primary(),[b])
        self.assertEqual(r["route_states"],{"PRIMARY_ONLY":1})
        self.assertEqual(r["source_states"]["PRIVATE_STALE_BATCH"],1)
    def test_actual_repository_market(self):
        root=Path(__file__).resolve().parents[2]
        path=root/"market/latest.json";body=path.read_bytes()
        c,r=route(body,[],as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(r["private_routes"],len(c))
        self.assertEqual(r["private_backup_components"],0)
        self.assertFalse(r["automatic_primary_replacement"])
        self.assertEqual(path.read_bytes(),body)
        print("V44_UNIFIED_MARKET_ROUTE_SUMMARY "+json.dumps(r,sort_keys=True))
