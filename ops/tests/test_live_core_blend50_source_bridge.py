import copy
import json
import unittest
from live_core_blend50_source_bridge import inspect,decode
from live_core_blend50_forward_seal import instant
class SourceBridgeTests(unittest.TestCase):
    def docs(self):
        now=instant("2026-12-01T10:00:00Z")
        ko="2026-12-01T12:00:00Z"
        g={"schema":"football-king-openligadb-hourly-v1","source":"OpenLigaDB","production_recommendations":"DISABLED","collected_utc":now.isoformat(),"matches":[{"league":"bundesliga","provider_match_id":1,"home":"A","away":"B","kickoff_utc":ko,"status":"SCHEDULED","score_ft":None,"crosscheck_state":"TWO_PUBLISHER_KICKOFF_AGREEMENT","crosscheck_provider":"TheSportsDB","source_id_pair":{"openligadb_match_id":1,"thesportsdb_event_id":"2","pair_basis":"LEAGUE_SCOPED_TEAMS_AND_KICKOFF"}}]}
        s={"schema":"football-king-extra-source-audit-v1","production_recommendations":"DISABLED","collected_utc":now.isoformat(),"sampled_fixtures":[{"league":"bundesliga","provider":"thesportsdb","provider_event_id":"2","home":"Alias A","away":"B","kickoff_utc":ko,"status":"SCHEDULED","score_ft":None}]}
        return now,g,s
    def test_structural_pair_never_admitted(self):
        now,g,s=self.docs();r=inspect(g,s,now=now)
        self.assertEqual(r["counts"]["timing_and_structure_candidates"],1)
        self.assertEqual(r["seal_inputs_emitted"],0)
        self.assertEqual(r["authenticated_forward_samples"],0)
        self.assertTrue(r["pair_hint_not_canonical_mapping"])
    def test_stale_secondary(self):
        now,g,s=self.docs();s["collected_utc"]="2026-12-01T03:00:00Z"
        r=inspect(g,s,now=now)
        self.assertEqual(r["counts"]["timing_and_structure_candidates"],0)
        self.assertEqual(r["overlapping_pair_blockers"]["SECONDARY_ENVELOPE_STALE"],1)
    def test_duplicate_and_missing_secondary(self):
        now,g,s=self.docs()
        s["sampled_fixtures"]*=2
        r=inspect(g,s,now=now)
        self.assertEqual(r["overlapping_pair_blockers"]["DUPLICATE_NATIVE_ID"],1)
        s["sampled_fixtures"]=[]
        self.assertEqual(inspect(g,s,now=now)["overlapping_pair_blockers"]["SECONDARY_ROW_NOT_UNIQUE"],1)
    def test_score_and_kickoff_conflicts(self):
        now,g,s=self.docs()
        s["sampled_fixtures"][0]["score_ft"]=[0,0]
        s["sampled_fixtures"][0]["kickoff_utc"]="2026-12-01T13:00:00Z"
        r=inspect(g,s,now=now)
        self.assertEqual(r["counts"]["pair_rows_structurally_consistent"],0)
        self.assertEqual(r["overlapping_pair_blockers"]["SECONDARY_NOT_PREMATCH"],1)
    def test_wrong_pin_and_future_clock(self):
        with self.assertRaisesRegex(ValueError,"BLOB_PIN_CHANGED"):decode(b"{}","0"*40)
        now,g,s=self.docs();g["collected_utc"]="2026-12-01T11:00:00Z"
        with self.assertRaisesRegex(ValueError,"FUTURE_CAPTURE"):inspect(g,s,now=now)
