import copy
import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from ops.shadow_forecast import predict_league
from ops.opponent_forward_capture import capture,attach,TOP_KEY,canonical
from ops.readonly_artifact_verify import verify_artifact
from ops.opponent_forward_audit import verified_artifacts
from unittest.mock import patch


class ReadonlyArtifactVerifyTest(unittest.TestCase):
    def setUp(self):
        start=datetime(2026,11,28,0,tzinfo=timezone.utc)
        rows=[]
        for i in range(60):
            d=date.fromordinal(date(2026,8,1).toordinal()+i)
            h,a=("Everton","Arsenal") if i%2==0 else ("Arsenal","Everton")
            rows.append({"league":"epl","date":d.isoformat(),"home":h,"away":a,
                         "score_ft":[2,1],"status":"FINISHED"})
        fixture={"date":"2026-11-28","home":"Everton","away":"Arsenal",
                 "event_id":"synthetic:artifact","status":"SCHEDULED",
                 "kickoff_utc":"2026-11-28T03:00:00+00:00"}
        preds=predict_league(rows+[fixture],"epl",start)
        shadow={"schema":"football-king-uncalibrated-shadow-1","status":"SHADOW_ONLY",
                "production_recommendations":"DISABLED","as_of_utc":start.isoformat(),
                "predictions_count":len(preds),"predictions":preds}
        finished={"schema":"football-king-single-source-finished-results-1",
                  "captured_utc":start.isoformat(),"production_recommendations":"DISABLED","records":rows}
        clock=iter([start,start+timedelta(minutes=1)])
        self.doc=attach(shadow,capture(shadow,finished,lambda:next(clock)))
        self.assertEqual(self.doc[TOP_KEY]["predictions_count"],1)
        self.manifest={"schema":"football-king-readonly-research-evidence-v1",
            "run_id":"123","run_attempt":"1","checkout_commit":"a"*40,"workflow_sha":"a"*40,
            "packaged_utc":(start+timedelta(minutes=2)).isoformat(),
            "candidate_count":1,"candidate_leagues":["epl"],
            "minimum_recorded_kickoff_lead_seconds":10680.0,
            "all_candidates_more_than_10min_at_packaging":True,
            "artifact_upload_time_independently_verified":False,"attestation_performed":False,
            "authenticated_forward_samples":0,"production_recommendations":"DISABLED"}
    def check(self,*,doc=None,manifest=None,extra=False,wrong_digest=False,run="123",include_bytes=False):
        doc=self.doc if doc is None else doc
        m=copy.deepcopy(self.manifest if manifest is None else manifest)
        raw=canonical(doc)+b"\n"
        m.update(shadow_sha256=hashlib.sha256(raw).hexdigest(),shadow_bytes=len(raw))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"artifact.zip"
            with zipfile.ZipFile(path,"w") as z:
                z.writestr("shadow.json",raw)
                z.writestr("manifest.json",json.dumps(m))
                if extra:
                    z.writestr("../unexpected","unsafe")
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            return verify_artifact(path,"0"*64 if wrong_digest else digest,run,"1",include_shadow_bytes=include_bytes)
    def test_valid_exact_bytes(self):
        doc,report=self.check()
        self.assertEqual(doc,self.doc)
        self.assertEqual(report["candidate_count"],1)
        self.assertEqual(report["authenticated_forward_samples"],0)
        self.assertFalse(report["attestation_verified"])
    def test_exact_raw_bytes_opt_in(self):
        doc,report,raw=self.check(include_bytes=True)
        self.assertEqual(raw,canonical(doc)+b"\n")
        self.assertEqual(hashlib.sha256(raw).hexdigest(),report["shadow_sha256"])

    def test_pinned_replay_duplicate_observations_not_certified(self):
        from ops.pinned_binding_replay import replay
        with tempfile.TemporaryDirectory() as tmp:
            specs=[]
            for run in ("123","124"):
                path=Path(tmp)/(run+".zip")
                raw=canonical(self.doc)+b"\n"
                manifest={**self.manifest,"run_id":run,
                          "shadow_sha256":hashlib.sha256(raw).hexdigest(),"shadow_bytes":len(raw)}
                with zipfile.ZipFile(path,"w") as z:
                    z.writestr("shadow.json",raw)
                    z.writestr("manifest.json",json.dumps(manifest))
                specs.append((path,hashlib.sha256(path.read_bytes()).hexdigest(),run,"1"))
            out=replay(specs)
            self.assertEqual(out["bound_observation_count"],2)
            self.assertEqual(out["distinct_exact_fixture_count"],1)
            self.assertEqual(out["repeated_observation_count"],1)
            self.assertEqual(out["authenticated_samples"],0)
            self.assertIsNone(out["formal_metrics"])
            self.assertFalse(out["actual_result_evidence_supplied"])
            with self.assertRaisesRegex(ValueError,"DUPLICATE_PINNED_RUN"):
                replay([specs[0],specs[0]])
            with self.assertRaisesRegex(ValueError,"ARTIFACT_DIGEST_MISMATCH"):
                replay([(*specs[0][:1],"0"*64,*specs[0][2:])])

    def test_wrong_digest_and_run(self):
        for kw in ({"wrong_digest":True},{"run":"124"},{"extra":True}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                self.check(**kw)
    def test_mutated_capture(self):
        doc=copy.deepcopy(self.doc)
        doc[TOP_KEY]["predictions"][0]["p"]=[.1,.8,.1]
        with self.assertRaises(ValueError):
            self.check(doc=doc)
    def test_misleading_manifest(self):
        for change in ({"authenticated_forward_samples":1},{"attestation_performed":True},
                       {"candidate_count":2},{"minimum_recorded_kickoff_lead_seconds":1},
                       {"packaged_utc":"2026-11-28T03:10:00+00:00"}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.check(manifest={**self.manifest,**change})

    def test_multiple_artifacts_verify_each_original_identity(self):
        first=("first.zip","a"*64,"123","1")
        second=("second.zip","b"*64,"124","1")
        with patch("ops.readonly_artifact_verify.verify_artifact",
                   side_effect=[(self.doc,{"candidate_count":1}),
                                (self.doc,{"candidate_count":1})]) as verifier:
            docs,reports=verified_artifacts([first,second])
            self.assertEqual(len(docs),2)
            self.assertEqual(len(reports),2)
            self.assertEqual([c.args for c in verifier.call_args_list],[first,second])

    def test_duplicate_run_and_excess_artifacts_fail_closed(self):
        first=("first.zip","a"*64,"123","1")
        second=("different.zip","b"*64,"123","1")
        with patch("ops.readonly_artifact_verify.verify_artifact",
                   return_value=(self.doc,{"candidate_count":1})):
            with self.assertRaisesRegex(ValueError,"DUPLICATE"):
                verified_artifacts([first,second])
            with self.assertRaisesRegex(ValueError,"TOO_MANY"):
                verified_artifacts([first]*5)

    def test_second_artifact_digest_failure_is_not_ignored(self):
        with patch("ops.readonly_artifact_verify.verify_artifact",
                   side_effect=[(self.doc,{"candidate_count":1}),ValueError("ARTIFACT_DIGEST_MISMATCH")]):
            with self.assertRaisesRegex(ValueError,"ARTIFACT_DIGEST_MISMATCH"):
                verified_artifacts([("a","a"*64,"123","1"),("b","b"*64,"124","1")])


if __name__=="__main__":
    unittest.main()
