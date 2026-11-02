"""Cross-check saved GitHub Actions ZIP against separately retrieved run metadata.

Synthetic metadata tests do not authenticate GitHub by themselves.
"""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_run_observation import publish
from research_observation_external_audit import audit
from ops.tests.test_research_run_observation import sample, NOW

REPO = "CHANCHUNWA1989/football-king-report"
SHA = "a" * 40
RUN = 12345
ARTIFACT = 99999


def stamp(seconds):
    return (NOW + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def record(raws, order=None):
    z=io.BytesIO()
    with ZipFile(z, "w", ZIP_DEFLATED) as archive:
        for name in (order or list(raws)):
            archive.writestr(name, raws[name])
    return z.getvalue()


class GithubExternalObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        source = self.folder / "research.json"
        source.write_text(json.dumps(sample()))
        saved = self.folder / "observation"
        publish(source, saved, run_id=str(RUN), attempt="1", sha=SHA, now=NOW)
        self.raws = {p.name:p.read_bytes() for p in saved.iterdir()}
        self.zip_bytes = record(self.raws)
        self.run = {
            "id": RUN, "run_attempt": 1,
            "repository": {"id": 42, "full_name": REPO},
            "head_repository":{"id":42, "full_name":REPO},
            "head_sha": SHA, "head_branch": "main",
            "path": ".github/workflows/football-king-iphone.yml",
            "status":"completed","conclusion":"success",
            "created_at":stamp(-120),"run_started_at":stamp(-100),
            "updated_at":stamp(120),
        }
        self.artifact = {
            "id": ARTIFACT,
            "name":"football-king-research-decision-observation",
            "expired":False,"created_at":stamp(5),
            "updated_at":stamp(6),
            "digest":"sha256:"+hashlib.sha256(self.zip_bytes).hexdigest(),
            "workflow_run":{
                "id":RUN, "repository_id":42, "head_repository_id":42,
                "head_branch":"main","head_sha":SHA,
            },
        }

    def check(self, z=None, run=None, artifact=None):
        return audit(self.zip_bytes if z is None else z,
                     self.run if run is None else run,
                     self.artifact if artifact is None else artifact,
                     now=NOW + timedelta(minutes=3))

    def test_actual_archived_bytes_and_external_run_identity_match(self):
        result=self.check()
        self.assertTrue(result["artifact_zip_digest_verified_against_metadata"])
        self.assertTrue(result["run_identity_consistent_with_metadata"])
        self.assertTrue(result["metadata_time_window_consistent"])
        self.assertEqual(result["run_id"],str(RUN))
        self.assertEqual(result["observed_count"],3)
        self.assertFalse(result["github_metadata_cryptographically_authenticated_by_tool"])
        self.assertFalse(result["chat_message_time_authenticated"])
        self.assertEqual(result["certified_forward_samples"],0)
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_hold_zero_observations_still_verifies(self):
        source=self.folder/"hold.json"
        doc=sample()
        doc.update(status="HOLD",selected_count=0,review_count=0,
                   model_only_count=0,selections=[],reviews=[],model_only_watchlist=[])
        source.write_text(json.dumps(doc))
        folder=self.folder/"hold"
        publish(source,folder,run_id=str(RUN),attempt="1",sha=SHA,now=NOW)
        z=record({p.name:p.read_bytes() for p in folder.iterdir()})
        art=copy.deepcopy(self.artifact)
        art["digest"]="sha256:"+hashlib.sha256(z).hexdigest()
        got=self.check(z=z,artifact=art)
        self.assertEqual(got["observed_count"],0)
        self.assertEqual(got["status"],"HOLD")

    def test_mutated_zip_or_wrong_github_archive_digest_rejected(self):
        z=self.zip_bytes+b"extra"
        with self.assertRaisesRegex(ValueError,"ZIP_DIGEST_MISMATCH"):
            self.check(z=z)
        wrong=copy.deepcopy(self.artifact)
        wrong["digest"]="sha256:"+"0"*64
        with self.assertRaisesRegex(ValueError,"ZIP_DIGEST_MISMATCH"):
            self.check(artifact=wrong)

    def test_forged_run_repository_commit_and_attempt_rejected(self):
        mutations=(
            ("id",RUN+1),("run_attempt",2),("head_sha","b"*40),
            ("head_branch","topic-branch"),("path",".github/workflows/other.yml"),
            ("conclusion","failure"),("status","in_progress")
        )
        for field,value in mutations:
            run=copy.deepcopy(self.run)
            run[field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(run=run)
        run=copy.deepcopy(self.run)
        run["repository"]["full_name"]="attacker/other-repo"
        with self.assertRaises(ValueError):
            self.check(run=run)

    def test_artifact_wrong_run_head_expired_or_name_rejected(self):
        for key,value in (("id",True),("name","another-artifact"),("expired",True)):
            a=copy.deepcopy(self.artifact)
            a[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(artifact=a)
        for field, value in (("id",222),("repository_id",15),("head_sha","0"*40)):
            a=copy.deepcopy(self.artifact)
            a["workflow_run"][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(artifact=a)

    def test_post_run_or_pre_run_observation_not_accepted(self):
        for field,value in (("created_at",stamp(-200)),
                            ("created_at",stamp(1000)),
                            ("updated_at",stamp(-5))):
            a=copy.deepcopy(self.artifact)
            a[field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(artifact=a)
        run=copy.deepcopy(self.run)
        run["run_started_at"]=stamp(60)
        with self.assertRaises(ValueError):
            self.check(run=run)

    def test_repacked_valid_zip_with_fake_new_manifest_not_signed(self):
        sources=copy.deepcopy(self.raws)
        observed=json.loads(sources["observation.json"])
        observed["certified_forward_samples"]=1
        sources["observation.json"]=json.dumps(observed).encode()
        z=record(sources)
        a=copy.deepcopy(self.artifact)
        a["digest"]="sha256:"+hashlib.sha256(z).hexdigest()
        with self.assertRaises(ValueError):
            self.check(z=z,artifact=a)

    def test_zip_path_traversal_duplicate_and_missing_files_rejected(self):
        for raws in (
            {"../source":b"x", **self.raws},
            {"observation.json":self.raws["observation.json"]},
            {**self.raws, "secret.txt":b"private"},
        ):
            z=record(raws)
            art=copy.deepcopy(self.artifact)
            art["digest"]="sha256:"+hashlib.sha256(z).hexdigest()
            with self.assertRaises(ValueError):
                self.check(z=z,artifact=art)
        zbuf=io.BytesIO()
        with ZipFile(zbuf,"w") as z:
            for n in ["observation.json","observation.json","research_selections.json"]:
                z.writestr(n,self.raws.get(n,b"x"))
        z=zbuf.getvalue()
        a=copy.deepcopy(self.artifact)
        a["digest"]="sha256:"+hashlib.sha256(z).hexdigest()
        with self.assertRaises(ValueError):
            self.check(z=z,artifact=a)

    def test_expired_artifact_and_missing_metadata_fail_closed(self):
        a=copy.deepcopy(self.artifact)
        a["expires_at"]=stamp(-1)
        with self.assertRaises(ValueError):
            self.check(artifact=a)
        a=copy.deepcopy(self.artifact)
        a.pop("digest")
        with self.assertRaises(ValueError):
            self.check(artifact=a)


if __name__=="__main__":
    unittest.main()
