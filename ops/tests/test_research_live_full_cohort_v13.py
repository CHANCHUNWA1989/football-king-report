"""Full-sized synthetic replay test: never real matches or production evidence."""
import json
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from ops.tests.test_research_live_intake_v4 import inputs
from ops.tests.test_research_live_evidence_v3 import final,FIN
from ops.tests.test_research_unified_live_v2 import NOW
from ops.tests.test_research_live_cohort_directory import write
from ops.research_live_pipeline_v10 import capture
from ops.research_live_cohort_directory import run

RELEASE="test"
START=datetime.fromisoformat("2026-10-01T00:00:00+00:00")
TEMPLATE=datetime.fromisoformat("2026-11-27T00:00:00+00:00")
CUT="2026-10-21T00:00:00Z"
END="2026-11-10T00:00:00Z"
AS_OF="2026-11-11T00:00:00Z"

def shifted(value,delta):
    if isinstance(value,dict):
        return {k:shifted(v,delta) for k,v in value.items()}
    if isinstance(value,list):
        return [shifted(v,delta) for v in value]
    if isinstance(value,str) and value.startswith("2026-11-27T"):
        return (datetime.fromisoformat(value.replace("Z","+00:00"))+delta).isoformat()
    return value

def make_case(i):
    day=i//8
    delta=START-TEMPLATE+timedelta(days=day,minutes=(i%8)*5)
    rows,policy=inputs()
    rows=shifted(rows,delta);policy=shifted(policy,delta)
    event="synthetic-"+str(i)
    fixture=policy["fixtures"].pop("synthetic")
    policy["fixtures"][event]=fixture
    for adapter in fixture["provider_ids"]:
        fixture["provider_ids"][adapter]+="-"+str(i)
    for row in rows:
        row["provider_fixture_id"]=fixture["provider_ids"][row["adapter"]]
        if row["kind"] in ("score","quote"):
            row["payload"].update(home=i%3,away=(i//3)%3,home_red=i%2,away_red=(i//2)%2)
    mode=i%2==0
    if mode:
        rows=[r for r in rows if r["kind"]!="quote"]
    raw=[json.dumps(r,sort_keys=True).encode() for r in rows]
    receipt=capture(raw,policy,event_id=event,as_of=shifted(NOW,delta),
                    model_release=RELEASE,probability_only=mode,source_bound=True)
    observations=shifted(final(),delta)
    h,a=i%3,(i//3)%3
    for obs in observations:
        obs.update(event_id=event,home=h+int(i%3==0),away=a+int(i%3==1))
    return dict(receipt=receipt,raw_captures=raw,policy=policy,
                final_observations=observations,settled_at=shifted(FIN,delta))

class FullCohortStressTests(unittest.TestCase):
    def test_320_source_bound_cases_through_directory_and_calibration(self):
        # 40 dates, 8 unique fixtures/date; 160/160 train/test.
        cases=[make_case(i) for i in range(320)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            write(root,cases)
            manifest_path=root/"manifest.json"
            manifest=json.loads(manifest_path.read_text())
            manifest.update(model_release=RELEASE,train_start=START.isoformat(),
                            train_cutoff=CUT,test_end=END)
            manifest_path.write_text(json.dumps(manifest),encoding="utf-8")
            report=run(root,as_of=AS_OF,require_source_binding=True)
        self.assertTrue(report["pipeline_replay_passed"])
        self.assertEqual(report["candidate_pairs"],320)
        self.assertEqual(report["source_bound_candidates"],320)
        self.assertEqual(report["probability_review"]["probability_only_count"],160)
        self.assertEqual(report["probability_review"]["with_market_snapshot_count"],160)
        self.assertIsNotNone(report["probability_review"]["metrics"]["descriptive_cluster_bootstrap_ci95"])
        c=report["calibration_research"]
        self.assertEqual((c["train_n"],c["test_n"]),(160,160))
        self.assertEqual((c["train_days"],c["test_days"]),(20,20))
        self.assertTrue(c["weights_fitted"])
        self.assertFalse(c["test_used_for_weight_selection"])
        self.assertEqual(c["test_metrics"]["blend"]["n"],160)
        self.assertEqual(report["authenticated_samples"],0)
        self.assertFalse(report["independent_oos_proven"])
        self.assertFalse(report["model_promotion_allowed"])
        self.assertFalse(report["certified_ev"])
        self.assertEqual(report["production_recommendations"],"DISABLED")
