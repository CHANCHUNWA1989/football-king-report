import json
import tempfile
import unittest
from pathlib import Path
from ops.red_card_forward_evidence import (
    canonical, sha, agree, archive_candidate, replay_candidate,
    xg_windows, fit_development, prospective_intake,
)

def fixture(key="f1", day="02"):
    d = dict(fixture_id=key, player_id="p1", publisher_id="league",
             origin_group="league", role="OFFICIAL", event_type="RED_CARD",
             side="AWAY", clock_s=1800, score=[1,0], prior_reds=[0,0],
             kickoff_utc=f"2026-01-{day}T12:00:00Z",
             event_utc=f"2026-01-{day}T12:30:00Z",
             captured_utc=f"2026-01-{day}T12:30:05Z")
    other = dict(d, publisher_id="publisher", origin_group="other", role="INDEPENDENT")
    shots = [dict(fixture_id=key, publisher_id="xg-provider", xg_model="v1",
                  clock_s=c, observed_utc=f"2026-01-{day}T12:{m}:00Z",
                  captured_utc=f"2026-01-{day}T12:{m}:05Z", home_xg=h, away_xg=a)
             for c,m,h,a in [(1200,"20",.2,.1),(1800,"30",.4,.3),(2400,"40",.8,.4)]]
    return canonical(d), canonical(other), shots

class RedCardEvidence(unittest.TestCase):
    def test_archive_replay_tamper_and_no_overwrite(self):
        a,b,_ = fixture()
        with tempfile.TemporaryDirectory() as temp:
            p = archive_candidate(temp,a,b)
            self.assertFalse(replay_candidate(p)["independently_verified"])
            with self.assertRaises(FileExistsError):
                archive_candidate(temp,a,b)
            (p/"official.json").write_bytes(a+b" ")
            with self.assertRaisesRegex(ValueError,"ARCHIVE_HASH_MISMATCH"):
                replay_candidate(p)

    def test_conflicts_and_shared_origin(self):
        a,b,_ = fixture()
        for changes in (dict(side="HOME"),dict(clock_s=1801),dict(origin_group="LEAGUE"),
                        dict(player_id="p2"),dict(score=[0,0]),dict(prior_reds=[1,0])):
            d=json.loads(b);d.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                agree(a,canonical(d))

    def test_xg_exposure_ratios(self):
        r=fit_development([fixture()],"2026-01-03T00:00:00Z")
        self.assertAlmostEqual(r["ratios"][0],.5)
        self.assertAlmostEqual(r["ratios"][1],2)
        self.assertFalse(r["model_calibration_verified"])

    def test_xg_missing_revised_or_changed(self):
        a,b,x=fixture()
        for changes in (dict(away_xg=.1),dict(xg_model="v2"),dict(fixture_id="f2"),
                        dict(clock_s=1800),dict(home_xg=float("nan"))):
            y=[dict(v) for v in x];y[2].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                xg_windows(a,b,y)
        with self.assertRaises(ValueError):
            xg_windows(a,b,x[:2])

    def test_training_cutoff_and_duplicates(self):
        with self.assertRaisesRegex(ValueError,"DEVELOPMENT_TIME_LEAKAGE"):
            fit_development([fixture()],"2026-01-02T12:35:00Z")
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            fit_development([fixture(),fixture()],"2026-01-03T00:00:00Z")

    def candidate(self):
        a,b,_=fixture("f2","04")
        p=dict(fixture_id="f2",official_sha256=sha(a),independent_sha256=sha(b),
               baseline_model="base-v1",challenger_model="card-v1",
               training_cutoff_utc="2026-01-03T00:00:00Z",
               prediction_utc="2026-01-04T12:30:10Z",
               baseline=[.5,.3,.2],challenger=[.6,.3,.1],
               external_witness_verified=True)
        f=dict(fixture_id="f2",status="FT",score=[2,0],
               final_utc="2026-01-04T14:00:00Z",
               captured_utc="2026-01-04T14:00:10Z",independently_verified=True)
        return a,b,p,f

    def intake(self,a,b,p,f,dev=("f1",)):
        return prospective_intake([(a,b,canonical(p),canonical(f))],
                                  cutoff="2026-01-03T00:00:00Z",
                                  development_fixture_ids=dev)

    def test_candidate_never_certifies_caller_flags(self):
        r=self.intake(*self.candidate())
        self.assertEqual(r["candidate_count"],1)
        self.assertEqual(r["true_prospective_count"],0)
        self.assertIsNone(r["log_loss"])
        self.assertFalse(r["promotion_allowed"])

    def test_prospective_leakage_or_hash_mismatch(self):
        a,b,p,f=self.candidate()
        for changes in (dict(prediction_utc="2026-01-04T14:00:00Z"),
                        dict(prediction_utc="2026-01-04T12:30:00Z"),
                        dict(official_sha256="fake"),dict(baseline=[.5,.5,.5])):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.intake(a,b,dict(p,**changes),f)
        with self.assertRaisesRegex(ValueError,"DEVELOPMENT_FIXTURE"):
            self.intake(a,b,p,f,dev=("f2",))

    def test_empty_intake_hold(self):
        r=prospective_intake([],cutoff="2026-01-03T00:00:00Z",development_fixture_ids=[])
        self.assertEqual(r["verified_count"],0)
        self.assertEqual(r["status"],"HOLD")

if __name__ == "__main__":
    unittest.main()
