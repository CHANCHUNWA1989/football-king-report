import unittest
from datetime import timedelta
from ops.v27_stack_archive import seal,audit,score,enc,sha
from ops.v9_league_weights import ANCHOR
from ops.v9_stacking_research import EXPERTS
from ops.tests.test_v6_forward_comparison import NOW,KO,result

def inputs():
    model={"schema":"v25-portable-stack-export-v1","status":"HOLD","production_recommendations":"DISABLED","verified_forward_sample_credit":0,"automatic_promotion":False,
        "model":{"schema":"v25-portable-stack-v1","experts":list(EXPERTS),"classes":[0,1,2],"coef":[[0.]*16 for _ in range(3)],"intercept":[0.,0.,0.],"temperature":1.,"stack_weight":.25}}
    q={k:[.5,.3,.2] for k in EXPERTS}
    src={"schema":"v25-native-stack-shadow-v1","status":"HOLD","production_recommendations":"DISABLED","verified_forward_sample_credit":0,"automatic_promotion":False,"date_convention":"Asia/Hong_Kong","future_intervening_results_unknown":True,"native_historical_identity_crosswalk_verified":False,
         "inference_as_of_utc":NOW.isoformat(),"generated_utc":NOW.isoformat(),"predictions_count":1,
         "source_receipts":[{"provider":"openligadb","season":year,"source":f"https://api.openligadb.de/getmatchdata/bl1/{year}","source_authenticated":False,"sha256":"a"*64,"bytes":100,"captured_utc":NOW.isoformat()} for year in (2025,2026)],
         "predictions":[{"event_id":"1","h":"2","a":"3","home":"H","away":"A","kickoff_utc":KO.isoformat(),"prediction_utc":NOW.isoformat(),"experts":q,"v10_weights":ANCHOR,"v10_prior_n":0,"v10_reference":[.5,.3,.2],"v10_1_stack":[.75*x+.25/3 for x in (.5,.3,.2)]}]}
    return model,src
class StackArchiveTests(unittest.TestCase):
    def test_archive_and_same_cut_scores(self):
        a,b=inputs();raw=seal(enc(a),enc(b),NOW)
        self.assertEqual(len(audit(raw,sha(raw))["rows"]),1)
        r=score(raw,sha(raw),enc(result()),KO+timedelta(hours=3))
        self.assertEqual(r["n"],1)
        self.assertEqual([r["metrics"][k]["correct"] for k in ("v5","v10","v10_1")],[1,1,1])
        self.assertEqual(r["verified_forward_sample_credit"],0)
    def test_tamper_probability_and_digest(self):
        a,b=inputs();raw=seal(enc(a),enc(b),NOW)
        with self.assertRaisesRegex(ValueError,"ARCHIVE_DIGEST"):audit(raw,"0"*64)
        b["predictions"][0]["v10_1_stack"]=[.9,.05,.05]
        with self.assertRaisesRegex(ValueError,"PROBABILITY_MISMATCH"):seal(enc(a),enc(b),NOW)
    def test_duplicate_and_late(self):
        a,b=inputs();b["predictions"].append(dict(b["predictions"][0]));b["predictions_count"]=2
        with self.assertRaisesRegex(ValueError,"FIXTURE_DUPLICATE"):seal(enc(a),enc(b),NOW)
        a,b=inputs();b["predictions"][0]["kickoff_utc"]=(NOW+timedelta(minutes=10)).isoformat()
        with self.assertRaisesRegex(ValueError,"FORECAST_CLOCK"):seal(enc(a),enc(b),NOW)
    def test_result_identity_conflict(self):
        a,b=inputs();raw=seal(enc(a),enc(b),NOW);doc=result();doc[0]["team1"]["teamId"]=8
        with self.assertRaisesRegex(ValueError,"RESULT_IDENTITY"):score(raw,sha(raw),enc(doc),KO+timedelta(hours=3))
