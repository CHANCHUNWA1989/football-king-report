"""Offline release rehearsal: actual CLI, gzip archival, and later score audit.

Synthetic fixture and score records only. No API, secrets, live match, real
attestation, deployment, or forward evidence credit.
"""
import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ops.shadow_forecast import predict_league
from ops.archive_prepare import prepare
from ops.opponent_forward_capture import TOP_KEY,attach
from ops.opponent_forward_audit import audit
from ops.source_publish_guard import PROVIDERS,LEAGUES

ROOT=Path(__file__).resolve().parents[2]
HK=ZoneInfo("Asia/Hong_Kong")


class OpponentReleaseRehearsal(unittest.TestCase):
    def test_actual_cli_archive_and_score_path(self):
        start=datetime.now(timezone.utc)
        local=start.astimezone(HK).date()
        kickoff=start+timedelta(hours=2)
        rows=[]
        for i in range(60):
            d=local-timedelta(days=61-i)
            h,a=("Everton","Arsenal") if i%2==0 else ("Arsenal","Everton")
            rows.append({"league":"epl","date":d.isoformat(),"home":h,"away":a,
                         "score_ft":[2,1],"status":"FINISHED"})
        future={"date":kickoff.astimezone(HK).date().isoformat(),"home":"Everton",
                "away":"Arsenal","event_id":"synthetic:release-rehearsal",
                "status":"SCHEDULED","kickoff_utc":kickoff.isoformat()}
        preds=predict_league(rows+[future],"epl",start)
        self.assertEqual(len(preds),1)
        shadow={"schema":"football-king-uncalibrated-shadow-1","status":"SHADOW_ONLY",
                "production_recommendations":"DISABLED","as_of_utc":start.isoformat(),
                "predictions_count":1,"predictions":preds}
        finished={"schema":"football-king-single-source-finished-results-1",
                  "captured_utc":start.isoformat(),"production_recommendations":"DISABLED","records":rows}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            site=root/"site";site.mkdir()
            snapshot=root/"snapshot";snapshot.mkdir()
            dest=root/"archive";dest.mkdir()
            path=site/"shadow.json"
            path.write_text(json.dumps(shadow),encoding="utf-8")
            initial=path.read_bytes()
            source=root/"finished.json";source.write_text(json.dumps(finished),encoding="utf-8")
            cap=root/"capture.json"
            out=snapshot/"shadow.json"
            def run(*args):
                result=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,
                                      capture_output=True,text=True,timeout=40)
                self.assertEqual(result.returncode,0,result.stdout+"\n"+result.stderr)
            run("ops/opponent_forward_capture.py","--shadow",path,"--finished",source,"--output",cap)
            run("ops/opponent_forward_capture.py","--shadow",path,"--capture",cap,"--output",out)
            self.assertEqual(path.read_bytes(),initial)
            packed=json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(packed[TOP_KEY]["predictions_count"],1)
            # As-of and market documents are harmless synthetic placeholders.
            for name in ("asof","paired"):
                (snapshot/(name+".json")).write_text('{"production_recommendations":"DISABLED"}',encoding="utf-8")
            created=prepare(snapshot,dest,"123","1",day=local.strftime("%Y/%m/%d"))
            self.assertEqual(len(created),3)
            self.assertEqual(prepare(snapshot,dest,"123","1",day=local.strftime("%Y/%m/%d")),[])
            archive=next((dest/"shadow").glob("**/*.json.gz"))
            self.assertEqual(gzip.decompress(archive.read_bytes()),out.read_bytes())
            archived=json.loads(gzip.decompress(archive.read_bytes()))
            # Synthetic later scoring clock, NOT the actual capture time.
            observed=kickoff+timedelta(hours=3)
            sources={"schema":"football-king-extra-source-audit-v1","production_recommendations":"DISABLED",
                     "six_league_independent_results_verified":False,"odds_fallback_confirmed":False,
                     "coverage_is_complete":False,"original_api_payload_redistributed":False,
                     "started_utc":observed.isoformat(),"collected_utc":(observed+timedelta(minutes=1)).isoformat(),
                     "providers":[],"sampled_fixtures":[]}
            for i,provider in enumerate(PROVIDERS):
                n=int(i<2)
                sources["providers"].append({"provider":provider,"status":"PARTIAL","configured":True,
                    "production_recommendations":"DISABLED","can_replace_1x2_market":False,
                    "original_bookmaker_odds_redistributed":False,"league_result_verification_complete":False,
                    "calls_attempted":n,"sampled_fixture_count":n,
                    "counts_by_league":{league:n if league=="epl" else 0 for league in LEAGUES}})
                if n:
                    sources["sampled_fixtures"].append({"provider":provider,"league":"epl","provider_event_id":str(i),
                        "home":"Everton","away":"Arsenal","kickoff_utc":kickoff.isoformat(),"status":"FINISHED","score_ft":[1,1]})
            report=audit([archived,archived],sources,observed+timedelta(minutes=2))
            self.assertEqual(report["two_publisher_exact_score_count"],1)
            self.assertEqual(report["authenticated_forward_samples"],0)
            self.assertEqual(report["recommendation_count"],0)
            self.assertFalse(report["positive_ev_verified"])
            self.assertEqual(report["production_recommendations"],"DISABLED")
            self.assertEqual(report["metrics"]["original"]["n"],1)
            self.assertEqual(report["metrics"]["candidate"]["n"],1)
            original=dict(archived);record=original.pop(TOP_KEY)
            self.assertEqual(attach(original,record),archived)
            print("OPPONENT_RELEASE_REHEARSAL="+json.dumps({
                "cli_capture":True,"cli_attach":True,"exact_gzip_bytes":True,
                "idempotent_archive":True,"synthetic_paired_cases":1,"real_forward_cases":0,
                "production_recommendations":"DISABLED"}))


if __name__=="__main__":
    unittest.main()
