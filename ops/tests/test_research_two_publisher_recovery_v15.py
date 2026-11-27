import json
import unittest
from pathlib import Path
from datetime import datetime,timezone
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.research_archive_score_recovery_v14 import targets,archive_snapshots
from ops.research_two_publisher_recovery_v15 import crosscheck,secondary_snapshots
from ops.source_publish_guard import PROVIDERS,LEAGUES

def secondary():
    row=dict(provider="thesportsdb",league="bundesliga",home="a",away="b",
             kickoff_utc="2026-11-01T15:00:00Z",provider_event_id="secondary1",status="FINISHED",score_ft=[2,1])
    providers=[]
    for p in PROVIDERS:
        counts={l:int(p=="thesportsdb" and l=="bundesliga") for l in LEAGUES}
        providers.append(dict(provider=p,status="PARTIAL",configured=True,production_recommendations="DISABLED",
            can_replace_1x2_market=False,original_bookmaker_odds_redistributed=False,league_result_verification_complete=False,
            calls_attempted=1,counts_by_league=counts,sampled_fixture_count=sum(counts.values())))
    return dict(schema="football-king-extra-source-audit-v1",production_recommendations="DISABLED",
        six_league_independent_results_verified=False,odds_fallback_confirmed=False,coverage_is_complete=False,
        original_api_payload_redistributed=False,started_utc="2026-11-01T18:00:00Z",collected_utc="2026-11-01T18:01:00Z",
        providers=providers,sampled_fixtures=[row])
def run(s):
    raw,p=fixture()
    return crosscheck(raw,[("primary",encode(p))],[("secondary",encode(s))],as_of="2026-11-02T00:00:00Z")
class TwoPublisherTests(unittest.TestCase):
    def test_exact(self):
        r=run(secondary())
        self.assertEqual(r["states"],{"TWO_PUBLISHER_EXACT_SCORE_CANDIDATE":1})
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["upstream_independence_proven"])
    def test_same_outcome_wrong_score(self):
        s=secondary();s["sampled_fixtures"][0]["score_ft"]=[3,1]
        self.assertEqual(run(s)["states"],{"CROSS_PUBLISHER_SCORE_CONFLICT":1})
    def test_wrong_kickoff(self):
        s=secondary();s["sampled_fixtures"][0]["kickoff_utc"]="2026-11-01T15:01:00Z"
        self.assertEqual(run(s)["states"],{"NO_SECOND_PUBLISHER_FINAL":1})
    def test_invalid_claim(self):
        s=secondary();s["six_league_independent_results_verified"]=True
        self.assertEqual(run(s)["invalid_secondary_snapshots"],1)
    def test_actual_archives(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json";raw=ledger.read_bytes();wanted=targets(raw)
        r=crosscheck(raw,archive_snapshots(root/"sources/live_germany/history",wanted),
            secondary_snapshots(root/"sources/history",wanted),as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(sum(r["states"].values()),len(wanted))
        self.assertEqual(r["authenticated_samples"],0)
        self.assertEqual(ledger.read_bytes(),raw)
        print("V15_TWO_PUBLISHER_SUMMARY "+json.dumps({k:r[k] for k in ("fixed_id_candidates","primary_snapshots_examined","secondary_snapshots_examined","invalid_secondary_snapshots","states","authenticated_samples")},sort_keys=True))
